"""SQLAlchemy ORM model for the Clinical Decision Support history store.

One table — ``clinical_decision_history`` — stores one row per clinical
analysis. Column types are portable (``JSON``, ``Text``, ``String``, ``Float``)
so the same model runs unchanged on SQLite (development) and PostgreSQL
(production); switching is purely a matter of the ``CLINICAL_DB_URL``
connection string, exactly as with the OCR-history and drug-interaction stores.
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
    """Declarative base for the clinical-decision module's tables."""


class ClinicalRecord(Base):
    """One persisted clinical decision-support analysis."""

    __tablename__ = "clinical_decision_history"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Optional link back to the OCR history record that triggered the analysis.
    source_record_id: Mapped[str | None] = mapped_column(
        String(32), default=None, index=True
    )

    # Inputs (denormalised, lowercased names for fast search/filter).
    medicines: Mapped[list] = mapped_column(JSON, default=list)
    medicine_names: Mapped[str] = mapped_column(Text, default="", index=True)
    medicine_count: Mapped[int] = mapped_column(Integer, default=0)

    # Outcome summary (cheap to read in list views + stats aggregation).
    top_disease: Mapped[str | None] = mapped_column(String(128), default=None)
    risk_level: Mapped[str] = mapped_column(String(16), default="low", index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    red_flag_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")

    # Full report payload (the ClinicalReport, serialised) for the detail view.
    report: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for list views."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "medicines": [m for m in self.medicine_names.split(",") if m],
            "medicine_count": self.medicine_count,
            "top_disease": self.top_disease,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "red_flag_count": self.red_flag_count,
            "summary": self.summary,
        }
