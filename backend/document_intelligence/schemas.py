"""Pydantic models for the Medical Document Intelligence API (frontend contract).

Generalizes prescription-only intake to every supported document type: lab
reports (Blood Test / CBC / LFT / KFT / Lipid Profile / Thyroid) get a
structured, per-test High/Low/Normal analysis; narrative documents (Discharge
Summary, Medical Certificate, Handwritten Prescription) get labeled sections.
Every document gets a RAG-grounded, LLM-or-offline clinical summary.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class DocumentType(str, Enum):
    """Every document type this module can classify and analyze."""

    HANDWRITTEN_PRESCRIPTION = "handwritten_prescription"
    BLOOD_TEST_REPORT = "blood_test_report"
    CBC_REPORT = "cbc_report"
    LFT_REPORT = "lft_report"
    KFT_REPORT = "kft_report"
    LIPID_PROFILE = "lipid_profile"
    THYROID_REPORT = "thyroid_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    MEDICAL_CERTIFICATE = "medical_certificate"
    UNKNOWN = "unknown"


# Document types analyzed as lab reports (structured test rows) rather than
# narrative sections.
LAB_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.BLOOD_TEST_REPORT,
        DocumentType.CBC_REPORT,
        DocumentType.LFT_REPORT,
        DocumentType.KFT_REPORT,
        DocumentType.LIPID_PROFILE,
        DocumentType.THYROID_REPORT,
    }
)


class DocumentClassification(BaseModel):
    """Outcome of automatic document-type detection."""

    document_type: DocumentType = DocumentType.UNKNOWN
    confidence: float = 0.0            # 0..1
    matched_keywords: list[str] = []
    auto_detected: bool = True         # False when the caller overrode the type


# ==========================================================================
# Lab report analysis
# ==========================================================================
class LabTestResult(BaseModel):
    """One detected test row from a lab report."""

    test_name: str
    value: float | None = None
    unit: str | None = None
    reference_range: str | None = None   # as stated on the report, or looked up
    ref_low: float | None = None
    ref_high: float | None = None
    status: str = "unknown"              # "high" | "low" | "normal" | "unknown"
    raw_line: str = ""


class LabReportAnalysis(BaseModel):
    """Structured result of analyzing a lab-style report."""

    results: list[LabTestResult] = []
    abnormal_count: int = 0
    total_count: int = 0


# ==========================================================================
# Narrative document fields
# ==========================================================================
class DocumentFields(BaseModel):
    """Common fields + a catch-all for document-type-specific sections."""

    patient_name: str | None = None
    age: str | None = None
    gender: str | None = None
    date: str | None = None
    doctor: str | None = None
    hospital: str | None = None
    # Labeled sections detected in the document (e.g. "Diagnosis", "Advice",
    # "Discharge Date", "Fit From", "Fit To") — key is the detected heading.
    sections: dict[str, str] = {}


# ==========================================================================
# Clinical summary (RAG + LLM, offline-safe)
# ==========================================================================
class PossibleMeaning(BaseModel):
    finding: str
    meaning: str


class ClinicalSummary(BaseModel):
    """AI-generated summary grounded in retrieved medical knowledge."""

    summary: str = ""
    abnormal_findings: list[str] = []
    possible_meanings: list[PossibleMeaning] = []
    follow_up_suggestions: list[str] = []
    ai_explanation: str = ""
    sources: list[str] = []
    confidence: float = 0.0            # 0..1, retrieval confidence
    provider: str = "offline"
    safety_note: str = ""


# ==========================================================================
# Analysis result (POST /documents/analyze)
# ==========================================================================
class DocumentAnalysisResult(BaseModel):
    """Full response of one document analysis."""

    id: str | None = None
    created_at: datetime | None = None
    filename: str | None = None
    document_type: DocumentType = DocumentType.UNKNOWN
    classification: DocumentClassification = DocumentClassification()
    raw_text: str = ""
    fields: DocumentFields = DocumentFields()
    lab_analysis: LabReportAnalysis | None = None
    clinical_summary: ClinicalSummary = ClinicalSummary()
    warnings: list[str] = []
    overall_confidence: float = 0.0    # 0..1
    processing_time: float = 0.0       # seconds
    has_image: bool = False


# ==========================================================================
# History (list / detail / stats) — same split as backend/history/schemas.py
# ==========================================================================
class DocumentHistoryItem(BaseModel):
    """Lightweight record used in the paginated history list view."""

    id: str
    created_at: datetime
    filename: str | None = None
    document_type: DocumentType = DocumentType.UNKNOWN
    abnormal_count: int = 0
    overall_confidence: float = 0.0
    processing_time: float = 0.0
    status: str = "success"            # "success" | "failed"
    has_image: bool = False


class DocumentHistoryDetail(DocumentHistoryItem):
    """Full record returned by GET /documents/{id}."""

    raw_text: str = ""
    fields: DocumentFields = DocumentFields()
    lab_analysis: LabReportAnalysis | None = None
    clinical_summary: ClinicalSummary = ClinicalSummary()
    classification: DocumentClassification = DocumentClassification()
    error: str | None = None


class DocumentHistoryPage(BaseModel):
    """A page of history items plus pagination metadata."""

    items: list[DocumentHistoryItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0


class DocumentStats(BaseModel):
    """Aggregate statistics for the dashboard cards."""

    total_analyses: int = 0
    successful_analyses: int = 0
    failed_analyses: int = 0
    by_document_type: dict[str, int] = {}
    total_abnormal_findings: int = 0
    average_confidence: float = 0.0


class DeleteResult(BaseModel):
    """Outcome of a delete / clear operation."""

    deleted: int = 0
    message: str = ""
