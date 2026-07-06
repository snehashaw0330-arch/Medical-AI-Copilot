"""SQLAlchemy ORM model for the Digital Twin snapshot store.

The twin itself is *derived* live from the existing report/OCR/clinical history —
it is never a separate source of truth. This table simply persists the latest
computed snapshot per patient so:

* ``GET /digital-twin/analytics`` can aggregate across patients cheaply, and
* the twin's evolution is durable (each recalculation upserts the snapshot).

Column types are portable (``JSON``, ``Text``, ``String``, ``Float``) so the same
model runs unchanged on SQLite (dev) and PostgreSQL (prod) — switching is purely
the ``DIGITAL_TWIN_DB_URL`` connection string, exactly like every other store.
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
    """Declarative base for the digital-twin module's tables."""


class TwinSnapshot(Base):
    """The latest computed Digital Twin for one patient (upserted on recalc)."""

    __tablename__ = "digital_twin_snapshots"

    # Patient slug is the primary key — one live snapshot per patient.
    patient_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    patient_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Denormalised headline metrics (cheap to aggregate for analytics).
    health_score: Mapped[float] = mapped_column(Float, default=0.0)
    health_status: Mapped[str] = mapped_column(String(16), default="stable")
    risk_level: Mapped[str] = mapped_column(String(16), default="low", index=True)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    top_disease: Mapped[str | None] = mapped_column(String(128), default=None)

    # Full serialised DigitalTwin for the detail view.
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for list/analytics views."""
        return {
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "computed_at": self.computed_at,
            "health_score": self.health_score,
            "health_status": self.health_status,
            "risk_level": self.risk_level,
            "report_count": self.report_count,
            "top_disease": self.top_disease,
        }
