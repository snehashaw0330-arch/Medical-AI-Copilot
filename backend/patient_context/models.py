"""SQLAlchemy ORM models for Patient Context & Conversation Memory.

Two tables:

* ``patient_contexts`` — one profile row per patient (identity + rollups:
  current medicines, known conditions, allergies, symptoms, follow-up
  recommendations, and the latest conversation summary).
* ``patient_events``   — one row per remembered fact or interaction,
  discriminated by ``event_type`` (ocr, medicine, disease_prediction,
  interaction, report, chat_message, summary, follow_up). A single composite
  index on (patient_id, event_type, created_at) serves every timeline/history
  query this module needs (conversation history, OCR history, medicine
  timeline, disease prediction timeline, ...) without per-type tables.

Column types are deliberately portable (JSON/Text/DateTime) so this runs
unchanged on SQLite (development) and PostgreSQL (production) — switching is
purely a connection-string change, matching every other persisted module in
this codebase (see ``backend/history/models.py``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    """Timezone-aware UTC now (stored naive-UTC for cross-DB consistency)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for the patient_context module's tables."""


class PatientContextRecord(Base):
    """One durable profile row per patient, keyed by a stable slug id."""

    __tablename__ = "patient_contexts"

    patient_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    patient_name: Mapped[str] = mapped_column(String(255), index=True)
    age: Mapped[int | None] = mapped_column(Integer, default=None)
    gender: Mapped[str | None] = mapped_column(String(16), default=None)

    current_medicines: Mapped[list] = mapped_column(JSON, default=list)
    known_conditions: Mapped[list] = mapped_column(JSON, default=list)
    allergies: Mapped[list] = mapped_column(JSON, default=list)
    symptoms: Mapped[list] = mapped_column(JSON, default=list)
    follow_up_recommendations: Mapped[list] = mapped_column(JSON, default=list)

    # Rolling AI summary of the conversation, refreshed by summary_engine.py
    # once enough new messages have accumulated since the last summary.
    last_summary: Mapped[str] = mapped_column(Text, default="")
    last_summary_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    messages_since_summary: Mapped[int] = mapped_column(Integer, default=0)

    # Copilot session ids observed for this patient (for cross-reference only;
    # copilot's own session store remains the source of truth for sessions).
    session_ids: Mapped[list] = mapped_column(JSON, default=list)
    event_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )


class PatientEventRecord(Base):
    """One remembered fact or conversation turn for a patient."""

    __tablename__ = "patient_events"
    __table_args__ = (
        Index("ix_patient_events_pid_type_created", "patient_id", "event_type", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4 hex
    patient_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # One of: ocr | medicine | disease_prediction | interaction | report
    #       | chat_message | summary | follow_up
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(16), default=None)  # chat_message only
    title: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source_session_id: Mapped[str | None] = mapped_column(String(64), default=None)
    source_ref_id: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )
