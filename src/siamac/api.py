"""API HTTP de integração.

O sistema principal dispara o evento, lê o resultado e — quando a leitura foi
para revisão — devolve o código correto pelo ``PATCH``. Toda correção vira uma
amostra de treino, o que faz da operação a fonte de rótulo mais barata que o
projeto tem.

Transporte é HTTP puro, sem TLS: rede interna, cliente único, serviço offline.
A compensação está nos dois binds — a API na interface interna com allowlist,
a configuração só em ``127.0.0.1``. Ver §5.2 do PLANO.md.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from .iso6346 import SIZE_TYPE_RE, validate
from .pipeline import Pipeline
from .storage import Event, EventStatus, OutboxItem, TrainingSample

__all__ = ["create_app"]


class TriggerRequest(BaseModel):
    gate: str = Field(default="in", pattern="^(in|out)$")
    external_ref: str | None = None
    #: Só no modo simulado: o código real, para o simulador gerar as leituras.
    truth: str | None = None


class CorrectionRequest(BaseModel):
    container_code: str
    iso_type: str | None = None
    corrected_by: str


class ReadOut(BaseModel):
    camera: str
    text: str
    mean_conf: float
    px_per_char: float | None


class EventOut(BaseModel):
    id: int
    created_at: dt.datetime
    gate: str
    external_ref: str | None
    status: str
    container_code: str | None
    iso_type: str | None
    confidence: float
    agreement: float
    check_digit_ok: bool
    reason: str
    condition: str
    corrected_by: str | None
    reads: list[ReadOut]

    @classmethod
    def of(cls, e: Event) -> EventOut:
        return cls(
            id=e.id, created_at=e.created_at, gate=e.gate, external_ref=e.external_ref,
            status=e.status, container_code=e.container_code, iso_type=e.iso_type,
            confidence=round(e.confidence, 4), agreement=round(e.agreement, 4),
            check_digit_ok=e.check_digit_ok, reason=e.reason, condition=e.condition,
            corrected_by=e.corrected_by,
            reads=[
                ReadOut(camera=r.camera, text=r.text,
                        mean_conf=round(r.mean_conf, 4), px_per_char=r.px_per_char)
                for r in e.reads
            ],
        )


def create_app(*, session_factory, pipeline: Pipeline, api_key: str | None = None) -> FastAPI:
    app = FastAPI(
        title="SiamacContainer",
        version="0.1.0",
        summary="Leitura automática de código ISO 6346 na portaria",
    )

    def require_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if api_key and x_api_key != api_key:
            raise HTTPException(401, "chave de API inválida ou ausente")

    guard = [Depends(require_key)]

    def _get(session, event_id: int) -> Event:
        event = session.get(Event, event_id)
        if event is None:
            raise HTTPException(404, f"evento {event_id} não existe")
        return event

    # ---- integração -------------------------------------------------------

    @app.post("/v1/events", status_code=201, dependencies=guard, tags=["eventos"])
    def trigger(req: TriggerRequest) -> EventOut:
        """Dispara uma leitura. O sistema principal chama quando o caminhão para."""
        if not req.truth:
            raise HTTPException(
                400,
                "backend simulado exige 'truth'. Com câmeras reais este campo "
                "não existe — a leitura vem do snapshot.",
            )
        processed = pipeline.process(
            truth=req.truth.upper(), gate=req.gate, external_ref=req.external_ref
        )
        with session_factory() as session:
            return EventOut.of(_get(session, processed.event_id))

    @app.get("/v1/events", dependencies=guard, tags=["eventos"])
    def list_events(
        status: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[EventOut]:
        """Lista eventos. ``status=NEEDS_REVIEW`` é a fila de correção humana."""
        stmt = select(Event).order_by(Event.id.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Event.status == status.upper())
        with session_factory() as session:
            return [EventOut.of(e) for e in session.scalars(stmt)]

    @app.get("/v1/events/{event_id}", dependencies=guard, tags=["eventos"])
    def get_event(event_id: int) -> EventOut:
        with session_factory() as session:
            return EventOut.of(_get(session, event_id))

    # ---- intervenção humana ----------------------------------------------

    @app.patch("/v1/events/{event_id}", dependencies=guard, tags=["revisão"])
    def correct(event_id: int, req: CorrectionRequest) -> EventOut:
        """Correção humana. Recusa código que não passa no dígito verificador."""
        result = validate(req.container_code)
        if not result.ok:
            raise HTTPException(422, f"código inválido: {result.reason}")
        if req.iso_type and not SIZE_TYPE_RE.match(req.iso_type.upper()):
            raise HTTPException(422, f"size/type inválido: {req.iso_type!r}")

        with session_factory() as session, session.begin():
            event = _get(session, event_id)
            event.container_code = result.code
            event.iso_type = req.iso_type.upper() if req.iso_type else None
            event.status = EventStatus.CORRECTED
            event.corrected_by = req.corrected_by
            event.corrected_at = dt.datetime.now(dt.UTC)
            event.check_digit_ok = True
            event.reason = "corrigido por operador"

            # Rotulagem de graça: cada correção vira treino para o próximo
            # fine-tune, inclusive as leituras que erraram.
            for r in event.reads:
                session.add(
                    TrainingSample(
                        event_id=event.id, camera=r.camera, ocr_text=r.text,
                        truth_text=result.code, px_per_char=r.px_per_char,
                        condition=event.condition,
                    )
                )

            session.add(
                OutboxItem(
                    event_id=event.id,
                    payload=json.dumps({
                        "event_id": event.id, "container_code": result.code,
                        "iso_type": event.iso_type, "gate": event.gate,
                        "external_ref": event.external_ref,
                        "source": "human", "corrected_by": req.corrected_by,
                    }),
                )
            )
            session.flush()
            return EventOut.of(event)

    @app.post("/v1/events/{event_id}/confirm", dependencies=guard, tags=["revisão"])
    def confirm(event_id: int, confirmed_by: str) -> EventOut:
        """Operador validou a leitura automática, sem alterar nada."""
        with session_factory() as session, session.begin():
            event = _get(session, event_id)
            if not event.container_code:
                raise HTTPException(409, "não há leitura para confirmar")
            event.status = EventStatus.CONFIRMED
            event.corrected_by = confirmed_by
            event.corrected_at = dt.datetime.now(dt.UTC)
            session.add(
                OutboxItem(
                    event_id=event.id,
                    payload=json.dumps({
                        "event_id": event.id, "container_code": event.container_code,
                        "gate": event.gate, "external_ref": event.external_ref,
                        "source": "confirmed", "corrected_by": confirmed_by,
                    }),
                )
            )
            session.flush()
            return EventOut.of(event)

    # ---- operação ---------------------------------------------------------

    @app.get("/v1/cameras/status", dependencies=guard, tags=["operação"])
    def cameras_status() -> list[dict]:
        from .cameras import px_per_char

        return [
            {
                "name": c.spec.name,
                "projection": c.spec.projection,
                "distance_m": c.spec.distance_m,
                "px_per_char": round(px_per_char(c.spec), 1),
                "alive": True,
            }
            for c in pipeline.cameras
        ]

    @app.get("/health", tags=["operação"])
    def health() -> dict:
        with session_factory() as session:
            pending = session.scalar(
                select(Event).where(Event.status == EventStatus.NEEDS_REVIEW).limit(1)
            )
            undelivered = session.scalars(
                select(OutboxItem).where(
                    OutboxItem.delivered_at.is_(None), OutboxItem.dead.is_(False)
                )
            ).all()
        return {
            "status": "ok",
            "ocr_backend": pipeline.ocr.name,
            "cameras": len(pipeline.cameras),
            "has_pending_review": pending is not None,
            "outbox_undelivered": len(undelivered),
        }

    return app
