"""Pydantic models for the Medical Report Generator API (frontend contract).

A *report* is a durable, exportable snapshot of one complete analysis: the OCR
output, the medicines detected, the disease prediction, the drug-interaction and
clinical-decision reports, the RAG context and all provenance — assembled once
and then rendered on demand as PDF, JSON or HTML.

The typed :class:`ReportContent` is the stable shape the React **Report Viewer**
consumes and the PDF/HTML renderers read. Nested sub-reports produced by other
modules (``drug_interactions``, ``clinical``) are carried as ``dict`` so the UI
can reuse their existing components verbatim without re-modelling them here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReportFormat(str, Enum):
    """Supported export formats."""

    PDF = "pdf"
    JSON = "json"
    HTML = "html"


# --------------------------------------------------------------------------
# Structured report content (the Report Viewer + renderer contract)
# --------------------------------------------------------------------------
class PatientInfo(BaseModel):
    """Patient / visit details parsed from the prescription (all optional)."""

    name: str | None = None
    age: str | None = None
    gender: str | None = None
    doctor: str | None = None
    hospital: str | None = None
    date: str | None = None
    diagnosis: str | None = None


class ReportMedicine(BaseModel):
    """One detected medicine, flattened for display + export."""

    name: str | None = None
    raw_text: str = ""
    confidence: float = 0.0            # 0..1 for this row
    dosage: str | None = None
    frequency: str | None = None
    duration: str | None = None
    needs_review: bool = False
    candidates: list[dict[str, Any]] = []   # alternative matches [{name, score}]
    uses: list[str] = []
    side_effects: list[str] = []


class RagDocument(BaseModel):
    """A retrieved knowledge-base chunk kept for provenance in the report."""

    source: str = ""
    text: str = ""
    score: float = 0.0


class ReportContent(BaseModel):
    """The full, structured content of one medical report."""

    # --- Header / meta ----------------------------------------------------
    title: str = "Medical Analysis Report"
    generated_at: datetime | None = None
    timestamp: str = ""               # human-readable, precomputed for renderers
    processing_time: float = 0.0      # seconds (the OCR analysis time)
    provider: str | None = None       # OCR provider/engine that produced the text
    engine: str | None = None
    filename: str | None = None
    has_image: bool = False

    # --- Sections (Requirement 2) -----------------------------------------
    patient: PatientInfo = PatientInfo()
    raw_text: str = ""                                 # OCR extracted text
    medicines: list[ReportMedicine] = []               # detected medicines
    overall_confidence: float = 0.0                    # 0..1
    disease_prediction: list[dict[str, Any]] = []      # from the clinical report
    drug_interactions: dict[str, Any] | None = None    # InteractionReport shape
    clinical: dict[str, Any] | None = None             # ClinicalReport shape
    recommendations: list[str] = []                    # AI recommendations
    warnings: list[str] = []
    contraindications: list[str] = []
    follow_up: list[str] = []
    rag_documents: list[RagDocument] = []              # retrieved RAG chunks
    sources: list[str] = []                            # provenance labels

    disclaimer: str = (
        "This AI-generated medical report is for educational and decision-support "
        "purposes only. It is not a medical diagnosis and may contain errors. "
        "Always verify against the original prescription and consult a qualified "
        "clinician or pharmacist before acting on any information here."
    )


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class ReportGenerateRequest(BaseModel):
    """Input for ``POST /reports/generate``.

    ``ocr_result`` is a serialised ``PrescriptionResult`` (the OCR endpoint's
    response) — it already carries the medicines, fields, raw text and, when
    available, the ``drug_interactions`` and ``clinical_report`` sub-reports. The
    builder extracts everything it needs from it. ``image_data_url`` optionally
    carries the prescription image (base64 data URL) so the report can retain it.
    """

    ocr_result: dict[str, Any] = Field(default_factory=dict)
    filename: str | None = None
    processing_time: float = 0.0
    source_record_id: str | None = None   # optional link to an OCR history record
    image_data_url: str | None = None     # optional base64 image for retention
    persist: bool = True


# --------------------------------------------------------------------------
# Responses (detail / list / stats)
# --------------------------------------------------------------------------
class ReportDetail(BaseModel):
    """Full report returned by ``POST /reports/generate`` and ``GET /reports/{id}``."""

    id: str
    created_at: datetime
    source_record_id: str | None = None
    content: ReportContent


class ReportItem(BaseModel):
    """Lightweight row for the reports list view."""

    id: str
    created_at: datetime
    filename: str | None = None
    patient_name: str | None = None
    medicine_count: int = 0
    overall_confidence: float = 0.0    # 0..1
    risk_level: str | None = None      # low | moderate | high | critical
    top_disease: str | None = None
    processing_time: float = 0.0
    has_image: bool = False


class ReportPage(BaseModel):
    """A page of report items plus pagination metadata."""

    items: list[ReportItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0


class ReportStats(BaseModel):
    """Aggregate statistics for the dashboard cards (Requirement 8)."""

    total_reports: int = 0
    reports_today: int = 0
    average_confidence: float = 0.0    # 0..1, over all reports
    high_risk_reports: int = 0         # risk_level in {high, critical}


class DeleteResult(BaseModel):
    """Outcome of a delete / clear operation."""

    deleted: int = 0
    message: str = ""
