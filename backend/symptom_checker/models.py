"""SQLAlchemy ORM model for the Symptom Checker history store.

One table — ``symptom_assessment_history`` — stores one row per triage
assessment. Column types are portable (``JSON``, ``Text``, ``String``,
``Float``) so the same model runs unchanged on SQLite (development) and
PostgreSQL (production); switching is purely a matter of the ``SYMPTOM_DB_URL``
connection string, exactly as with the other history stores in this project.
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
    """Declarative base for the symptom-checker module's tables."""


class AssessmentRecord(Base):
    """One persisted symptom-checker & triage assessment."""

    __tablename__ = "symptom_assessment_history"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Inputs (denormalised, lowercased for fast search/filter).
    symptom_names: Mapped[str] = mapped_column(Text, default="", index=True)
    symptom_count: Mapped[int] = mapped_column(Integer, default=0)
    severity_input: Mapped[int] = mapped_column(Integer, default=5)
    duration: Mapped[str | None] = mapped_column(String(32), default=None)

    # Outcome summary (cheap to read in list views + aggregation).
    top_condition: Mapped[str | None] = mapped_column(String(128), default=None)
    urgency_level: Mapped[str] = mapped_column(String(16), default="self_care", index=True)
    severity_level: Mapped[str] = mapped_column(String(16), default="mild")
    triage_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Full report payload (the TriageAssessment, serialised) for the detail view.
    report: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for list views."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "symptoms": [s for s in self.symptom_names.split(",") if s],
            "symptom_count": self.symptom_count,
            "top_condition": self.top_condition,
            "urgency_level": self.urgency_level,
            "severity_level": self.severity_level,
            "triage_score": self.triage_score,
        }
