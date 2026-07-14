"""SQLAlchemy ORM models for the Medical Document Intelligence module.

A single table — ``document_records`` — stores one row per analyzed document
(lab report, discharge summary, medical certificate, handwritten
prescription, ...). Column types mirror ``backend/history/models.py`` so the
same model runs unchanged on SQLite (development) and PostgreSQL (production).
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
    """Declarative base for the document-intelligence module's tables."""


class DocumentRecord(Base):
    """One document analysis, success or failure."""

    __tablename__ = "document_records"

    # Identity + time
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    # Source file
    filename: Mapped[str | None] = mapped_column(String(255), default=None)
    file_path: Mapped[str | None] = mapped_column(String(512), default=None)

    # Classification
    document_type: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Extraction + parsing
    raw_text: Mapped[str] = mapped_column(Text, default="")
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    lab_results: Mapped[dict] = mapped_column(JSON, default=dict)   # LabReportAnalysis, or {}
    abnormal_count: Mapped[int] = mapped_column(Integer, default=0)

    # Clinical summary
    clinical_summary: Mapped[dict] = mapped_column(JSON, default=dict)

    # Quality / provenance
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    processing_time: Mapped[float] = mapped_column(Float, default=0.0)     # seconds

    # Outcome
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    def summary(self) -> dict:
        """Lightweight projection for list views (omits heavy text/JSON blobs)."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "filename": self.filename,
            "document_type": self.document_type,
            "abnormal_count": self.abnormal_count,
            "overall_confidence": self.overall_confidence,
            "processing_time": self.processing_time,
            "status": self.status,
            "has_image": bool(self.file_path),
        }

    def detail(self) -> dict:
        """Full projection for the single-record detail view."""
        return {
            **self.summary(),
            "raw_text": self.raw_text,
            "fields": self.fields or {},
            "lab_analysis": self.lab_results or None,
            "clinical_summary": self.clinical_summary or {},
            "classification": {
                "document_type": self.document_type,
                "confidence": self.classification_confidence,
                "matched_keywords": [],
                "auto_detected": True,
            },
            "error": self.error,
        }
