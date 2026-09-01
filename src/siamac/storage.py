"""Persistência: SQLite via SQLAlchemy.

Quatro tabelas. ``events`` é o registro do que passou pela portaria,
``reads`` guarda o que cada câmera leu (é o que permite auditar uma
divergência depois), ``outbox`` garante que nada se perde se o sistema
principal cair, e ``training_samples`` acumula as correções humanas — que são
rotulagem de graça vinda da operação.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

__all__ = [
    "Base",
    "Event",
    "EventStatus",
    "OutboxItem",
    "Read",
    "TrainingSample",
    "make_engine",
    "make_session_factory",
]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class EventStatus(StrEnum):
    PENDING = "PENDING"
    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CORRECTED = "CORRECTED"
    CONFIRMED = "CONFIRMED"


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    gate: Mapped[str] = mapped_column(String(16), default="in")
    external_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=EventStatus.PENDING, index=True)
    container_code: Mapped[str | None] = mapped_column(String(11), nullable=True, index=True)
    iso_type: Mapped[str | None] = mapped_column(String(4), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    agreement: Mapped[float] = mapped_column(Float, default=0.0)
    check_digit_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    condition: Mapped[str] = mapped_column(String(32), default="")

    corrected_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    reads: Mapped[list[Read]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Read(Base):
    __tablename__ = "reads"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    camera: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String(32), default="")
    mean_conf: Mapped[float] = mapped_column(Float, default=0.0)
    px_per_char: Mapped[float | None] = mapped_column(Float, nullable=True)

    event: Mapped[Event] = relationship(back_populates="reads")


class OutboxItem(Base):
    """Entrega ao sistema principal, com retry. Nada de POST otimista."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    payload: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dead: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class TrainingSample(Base):
    """Par (recorte, texto correto) gerado por uma correção humana."""

    __tablename__ = "training_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    camera: Mapped[str] = mapped_column(String(16))
    crop_path: Mapped[str] = mapped_column(String(255), default="")
    ocr_text: Mapped[str] = mapped_column(String(32), default="")
    truth_text: Mapped[str] = mapped_column(String(32))
    px_per_char: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition: Mapped[str] = mapped_column(String(32), default="")


def make_engine(url: str = "sqlite:///siamac.db", *, echo: bool = False):
    engine = create_engine(url, echo=echo, future=True)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
