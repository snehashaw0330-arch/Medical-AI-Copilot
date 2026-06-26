"""SQLAlchemy ORM models for the OCR History module.

A single table — ``ocr_history`` — stores one row per prescription analysis.
The column types (``JSON``, ``Text``, ``DateTime``) are deliberately portable
so the same model runs unchanged on SQLite (development) and PostgreSQL
(production); switching is purely a matter of the connection URL.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    """Timezone-aware UTC now (stored naive-UTC for cross-DB consistency)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for the history module's tables."""


class OCRRecord(Base):
    """One prescription OCR analysis, success or failure."""

    __tablename__ = "ocr_history"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Source image
    filename: Mapped[str | None] = mapped_column(String(255), default=None)
    image_path: Mapped[str | None] = mapped_column(String(512), default=None)

    # OCR output
    raw_text: Mapped[str] = mapped_column(Text, default="")
    # Full structured medicines (list of dicts) for the detail view + PDF/JSON.
    medicines: Mapped[list] = mapped_column(JSON, default=list)
    # Denormalised, lowercased medicine names for fast search / filtering.
    medicine_names: Mapped[str] = mapped_column(Text, default="", index=True)
    medicine_count: Mapped[int] = mapped_column(Integer, default=0)
    # Parsed patient/visit fields + doctor notes (kept for the detail view).
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    doctor_notes: Mapped[list] = mapped_column(JSON, default=list)

    # Quality / provenance
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    engine: Mapped[str | None] = mapped_column(String(64), default=None)
    provider: Mapped[str | None] = mapped_column(String(64), default=None)
    processing_time: Mapped[float] = mapped_column(Float, default=0.0)  # seconds

    # Outcome
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    def summary(self) -> dict:
        """Lightweight projection for list views (omits heavy text/medicines)."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "filename": self.filename,
            "medicine_count": self.medicine_count,
            "medicine_names": [m for m in self.medicine_names.split(",") if m],
            "confidence": self.confidence,
            "engine": self.engine,
            "processing_time": self.processing_time,
            "status": self.status,
            "has_image": bool(self.image_path),
        }

    def detail(self) -> dict:
        """Full projection for the single-record detail view."""
        return {
            **self.summary(),
            "raw_text": self.raw_text,
            "medicines": self.medicines or [],
            "fields": self.fields or {},
            "doctor_notes": self.doctor_notes or [],
            "provider": self.provider,
            "error": self.error,
        }
