"""SQLAlchemy ORM model for the Medicine Recommendation history store.

One table — ``medicine_recommendation_history`` — stores one row per report.
Column types are portable (``JSON``, ``Text``, ``String``, ``Float``) so the
same model runs unchanged on SQLite (development) and PostgreSQL (production);
switching is purely a matter of the ``MEDICINE_REC_DB_URL`` connection string,
exactly as with the other history stores in this project.
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
    """Declarative base for the medicine-recommendation module's tables."""


class RecommendationRecord(Base):
    """One persisted medicine-recommendation report."""

    __tablename__ = "medicine_recommendation_history"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Optional link back to the OCR history record that triggered the report.
    source_record_id: Mapped[str | None] = mapped_column(
        String(32), default=None, index=True
    )

    # Inputs (denormalised, lowercased for fast search/filter).
    medicine_names: Mapped[str] = mapped_column(Text, default="", index=True)
    medicine_count: Mapped[int] = mapped_column(Integer, default=0)

    # Outcome summary (cheap to read in list views).
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Full report payload (the RecommendationReport, serialised) for the detail view.
    report: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for list views."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "medicines": [m for m in self.medicine_names.split(",") if m],
            "medicine_count": self.medicine_count,
            "overall_confidence": self.overall_confidence,
        }
