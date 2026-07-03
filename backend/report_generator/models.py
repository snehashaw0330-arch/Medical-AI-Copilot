"""SQLAlchemy ORM model for the Medical Report Generator store.

One table — ``medical_reports`` — stores one row per generated report. Column
types are portable (``JSON``, ``Text``, ``String``, ``Float``) so the same model
runs unchanged on SQLite (development) and PostgreSQL (production); switching is
purely a matter of the ``REPORTS_DB_URL`` connection string, exactly as with the
OCR-history, drug-interaction and clinical-decision stores.

The full structured ``ReportContent`` is stored in the ``content`` JSON column;
the scalar columns alongside it are denormalised projections that make list
views, search/filtering and dashboard aggregation cheap.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    """Timezone-aware UTC now, stored naive-UTC for cross-DB consistency."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for the report-generator module's tables."""


class ReportRecord(Base):
    """One persisted, exportable medical report."""

    __tablename__ = "medical_reports"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Optional link back to the OCR history record that produced this report.
    source_record_id: Mapped[str | None] = mapped_column(
        String(32), default=None, index=True
    )

    # Source image (a retained copy, like the OCR-history store).
    filename: Mapped[str | None] = mapped_column(String(255), default=None)
    image_path: Mapped[str | None] = mapped_column(String(512), default=None)

    # Denormalised, searchable projections of the content.
    patient_name: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    medicine_names: Mapped[str] = mapped_column(Text, default="", index=True)
    medicine_count: Mapped[int] = mapped_column(Integer, default=0)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)   # 0..1
    risk_level: Mapped[str | None] = mapped_column(String(16), default=None, index=True)
    top_disease: Mapped[str | None] = mapped_column(String(128), default=None)
    processing_time: Mapped[float] = mapped_column(Float, default=0.0)      # seconds

    # Full structured report payload (the ReportContent, serialised).
    content: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for list views."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "filename": self.filename,
            "patient_name": self.patient_name,
            "medicine_count": self.medicine_count,
            "overall_confidence": self.overall_confidence,
            "risk_level": self.risk_level,
            "top_disease": self.top_disease,
            "processing_time": self.processing_time,
            "has_image": bool(self.image_path),
        }

    def detail(self) -> dict:
        """Full projection for the single-report detail view / viewer."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "source_record_id": self.source_record_id,
            "content": self.content or {},
        }
