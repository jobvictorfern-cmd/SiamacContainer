"""O caminho de um evento: captura → recorte → OCR → fusão → decisão → banco.

Este módulo é o mesmo em produção e no protótipo. O que muda é o que foi
injetado nele: câmeras simuladas e OCR simulado aqui, snapshot HTTP e ONNX
Runtime lá. Nenhuma linha abaixo sabe a diferença.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass

from .cameras import FrameSource, pick_condition
from .fusion import Decision, FusionResult, OcrRead, fuse
from .ocr import OcrBackend
from .storage import Event, EventStatus, OutboxItem, Read

__all__ = ["Pipeline", "PipelineConfig", "ProcessedEvent"]


@dataclass(slots=True)
class PipelineConfig:
    min_confidence: float = 0.75
    min_agreement: float = 0.60
    #: Quantos quadros por câmera. Com o veículo parado, uma rajada curta
    #: custa quase nada e cobre o quadro que saiu borrado.
    burst: int = 3


@dataclass(slots=True)
class ProcessedEvent:
    event_id: int | None
    fusion: FusionResult
    reads: list[OcrRead]
    condition: str


class Pipeline:
    def __init__(
        self,
        cameras: list[FrameSource],
        ocr: OcrBackend,
        *,
        config: PipelineConfig | None = None,
        session_factory=None,
        rng: random.Random | None = None,
    ) -> None:
        self.cameras = cameras
        self.ocr = ocr
        self.config = config or PipelineConfig()
        self.session_factory = session_factory
        self._rng = rng or random.Random()

    # ---- captura ----------------------------------------------------------

    def _best_read(self, camera: FrameSource, truth: str, condition) -> OcrRead:
        """Rajada curta; fica com a leitura de maior confiança média.

        Selecionar por confiança, e não pelo primeiro quadro, é o que compra a
        robustez contra um quadro borrado sem custar nada em latência.
        """
        best: OcrRead | None = None
        for _ in range(max(1, self.config.burst)):
            crop = camera.grab(truth=truth, condition=condition)
            read = self.ocr.read(crop, camera=camera.spec.name)
            if best is None or read.mean_conf > best.mean_conf:
                best = read
        assert best is not None
        return best

    # ---- processamento ----------------------------------------------------

    def process(
        self,
        *,
        truth: str,
        gate: str = "in",
        external_ref: str | None = None,
        condition: tuple[str, float] | None = None,
        persist: bool = True,
    ) -> ProcessedEvent:
        cond = condition or pick_condition(self._rng)

        reads = [self._best_read(cam, truth, cond) for cam in self.cameras]
        result = fuse(
            reads,
            min_confidence=self.config.min_confidence,
            min_agreement=self.config.min_agreement,
        )

        event_id = None
        if persist and self.session_factory is not None:
            event_id = self._persist(result, reads, cond[0], gate, external_ref)

        return ProcessedEvent(event_id=event_id, fusion=result, reads=reads, condition=cond[0])

    def _persist(
        self,
        result: FusionResult,
        reads: list[OcrRead],
        condition: str,
        gate: str,
        external_ref: str | None,
    ) -> int:
        status = (
            EventStatus.AUTO_ACCEPTED
            if result.decision is Decision.AUTO_ACCEPT
            else EventStatus.NEEDS_REVIEW
        )

        with self.session_factory() as session, session.begin():
            event = Event(
                gate=gate,
                external_ref=external_ref,
                status=status,
                container_code=result.code or None,
                confidence=result.confidence,
                agreement=result.agreement,
                check_digit_ok=result.check_digit_ok,
                reason=result.reason,
                condition=condition,
            )
            event.reads = [
                Read(
                    camera=r.camera,
                    text=r.text,
                    mean_conf=r.mean_conf,
                    px_per_char=r.px_per_char,
                )
                for r in reads
            ]
            session.add(event)
            session.flush()

            # Só o que foi aceito automaticamente sai agora. O que precisa de
            # revisão só é entregue depois que um humano confirmar — entregar
            # uma leitura duvidosa como se fosse boa é o erro que o sistema
            # existe para não cometer.
            if status is EventStatus.AUTO_ACCEPTED:
                session.add(
                    OutboxItem(
                        event_id=event.id,
                        payload=json.dumps(
                            {
                                "event_id": event.id,
                                "container_code": event.container_code,
                                "gate": event.gate,
                                "external_ref": event.external_ref,
                                "confidence": round(event.confidence, 4),
                                "source": "auto",
                            }
                        ),
                    )
                )
            return event.id
