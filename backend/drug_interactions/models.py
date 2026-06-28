"""SQLAlchemy ORM model for the Drug Interaction history store.

One table — ``drug_interaction_history`` — stores one row per analysis. Column
types are portable (``JSON``, ``Text``, ``String``) so the same model runs
unchanged on SQLite (development) and PostgreSQL (production); switching is
purely a matter of the ``INTERACTIONS_DB_URL`` connection string.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    """Timezone-aware UTC now, stored naive-UTC for cross-DB consistency."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for the drug-interaction module's tables."""


class InteractionRecord(Base):
    """One persisted drug-interaction analysis."""

    __tablename__ = "drug_interaction_history"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Optional link back to the OCR history record that triggered the analysis.
    source_record_id: Mapped[str | None] = mapped_column(String(32), default=None, index=True)

    # Inputs (denormalised, lowercased names for fast search/filter).
    medicines: Mapped[list] = mapped_column(JSON, default=list)
    medicine_names: Mapped[str] = mapped_column(Text, default="", index=True)
    medicine_count: Mapped[int] = mapped_column(Integer, default=0)

    # Outcome summary (cheap to read in list views).
    overall_risk: Mapped[str] = mapped_column(String(16), default="none", index=True)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")

    # Full report payload (the InteractionReport, serialised) for the detail view.
    report: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for list views."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "medicines": [m for m in self.medicine_names.split(",") if m],
            "medicine_count": self.medicine_count,
            "interaction_count": self.interaction_count,
            "overall_risk": self.overall_risk,
            "summary": self.summary,
        }
