"""SQLAlchemy ORM model for the Prescription Validation history store.

One table — ``prescription_validation_history`` — stores one row per validation.
Column types are portable (``JSON``, ``Text``, ``String``, ``Float``) so the same
model runs unchanged on SQLite (development) and PostgreSQL (production);
switching is purely a matter of the ``VALIDATION_DB_URL`` connection string,
exactly as with the OCR-history, drug-interaction and clinical stores.
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
    """Declarative base for the prescription-validation module's tables."""


class ValidationRecord(Base):
    """One persisted prescription-validation analysis."""

    __tablename__ = "prescription_validation_history"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Optional link back to the OCR history record that triggered the validation.
    source_record_id: Mapped[str | None] = mapped_column(
        String(32), default=None, index=True
    )

    # Inputs (denormalised, lowercased names for fast search/filter).
    medicine_names: Mapped[str] = mapped_column(Text, default="", index=True)
    medicine_count: Mapped[int] = mapped_column(Integer, default=0)

    # Outcome summary (cheap to read in list views + aggregation).
    validation_score: Mapped[float] = mapped_column(Float, default=100.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="safe", index=True)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")

    # Full report payload (the ValidationReport, serialised) for the detail view.
    report: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for list views."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "medicines": [m for m in self.medicine_names.split(",") if m],
            "medicine_count": self.medicine_count,
            "validation_score": self.validation_score,
            "risk_level": self.risk_level,
            "issue_count": self.issue_count,
            "summary": self.summary,
        }
