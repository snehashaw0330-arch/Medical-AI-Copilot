"""SQLAlchemy ORM models for the AI Governance store.

Four portable tables (``JSON``/``Text``/``String``/``Float``/``DateTime`` only,
so the same models run unchanged on SQLite in development and PostgreSQL in
production — switching is purely the ``AI_GOVERNANCE_DB_URL`` connection string,
exactly like every other store in this project):

* ``ai_decision_traces`` — one reproducible record per AI decision. The full
  trace lives in the ``trace`` JSON column; scalar columns beside it are
  denormalised projections that make search + dashboard aggregation cheap.
* ``audit_logs``          — one row per API request (written in the background).
* ``model_registry``      — every AI model, its version, accuracy and status.
* ``dataset_registry``    — every dataset, its version, source, size and purpose.
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
    """Declarative base for the governance module's tables."""


class DecisionTraceRecord(Base):
    """One persisted, reproducible AI decision trace."""

    __tablename__ = "ai_decision_traces"

    trace_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )
    # Idempotency key when a trace is derived from a medical report.
    source_report_id: Mapped[str | None] = mapped_column(
        String(40), default=None, index=True, unique=False
    )

    # Denormalised, searchable projections.
    patient_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    patient_name: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    medicine_names: Mapped[str] = mapped_column(Text, default="", index=True)
    medicine_count: Mapped[int] = mapped_column(Integer, default=0)
    top_disease: Mapped[str | None] = mapped_column(String(160), default=None, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, index=True)  # 0..1
    status: Mapped[str] = mapped_column(String(20), default="success", index=True)
    execution_time: Mapped[float] = mapped_column(Float, default=0.0)          # seconds
    model_version: Mapped[str] = mapped_column(String(64), default="", index=True)
    dataset_version: Mapped[str] = mapped_column(String(64), default="", index=True)

    # Full serialised DecisionTrace.
    trace: Mapped[dict] = mapped_column(JSON, default=dict)

    def item(self) -> dict:
        """Lightweight projection for the list / search view."""
        return {
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "patient_name": self.patient_name,
            "top_disease": self.top_disease,
            "medicine_count": self.medicine_count,
            "confidence": self.confidence,
            "status": self.status,
            "execution_time": self.execution_time,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
        }


class AuditLogRecord(Base):
    """One audited API request (written in the background, best-effort)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )
    user: Mapped[str] = mapped_column(String(120), default="system", index=True)
    method: Mapped[str] = mapped_column(String(10), default="")
    api: Mapped[str] = mapped_column(String(400), default="", index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=0, index=True)
    processing_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    model_used: Mapped[str | None] = mapped_column(String(80), default=None)
    prompt: Mapped[str | None] = mapped_column(Text, default=None)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, default=None, index=True)

    def item(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "user": self.user,
            "method": self.method,
            "api": self.api,
            "status_code": self.status_code,
            "processing_time_ms": self.processing_time_ms,
            "model_used": self.model_used,
            "prompt": self.prompt,
            "sources": self.sources or [],
            "warnings": self.warnings or [],
            "error": self.error,
        }


class ModelRecord(Base):
    """A registered AI model + its provenance."""

    __tablename__ = "model_registry"

    # (name, version) uniquely identifies a model release. We key on the pair.
    key: Mapped[str] = mapped_column(String(160), primary_key=True)  # "name@version"
    name: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(64))
    accuracy: Mapped[float | None] = mapped_column(Float, default=None)  # 0..1
    training_date: Mapped[str | None] = mapped_column(String(40), default=None)
    dataset: Mapped[str | None] = mapped_column(String(160), default=None)
    status: Mapped[str] = mapped_column(String(20), default="production", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def item(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "accuracy": self.accuracy,
            "training_date": self.training_date,
            "dataset": self.dataset,
            "status": self.status,
            "description": self.description,
            "updated_at": self.updated_at,
        }


class DatasetRecord(Base):
    """A registered dataset + its provenance."""

    __tablename__ = "dataset_registry"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)  # "name@version"
    name: Mapped[str] = mapped_column(String(140), index=True)
    version: Mapped[str] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(300), default=None)
    size: Mapped[str | None] = mapped_column(String(60), default=None)
    date_added: Mapped[str | None] = mapped_column(String(40), default=None)
    purpose: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def item(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "size": self.size,
            "date_added": self.date_added,
            "purpose": self.purpose,
            "updated_at": self.updated_at,
        }
