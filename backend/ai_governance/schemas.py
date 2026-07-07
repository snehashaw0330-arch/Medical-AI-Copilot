"""Pydantic v2 contracts for the AI Governance, Audit & Explainability module.

These are the stable shapes the React governance pages consume and the router
returns. They model five concerns:

* **AI Decision Trace** — the full, reproducible record of one prediction.
* **Explainability** — human-readable "why" behind every sub-decision.
* **Confidence analysis** — reliability, calibration, evidence, uncertainty.
* **Pipeline view** — the per-step execution graph (time / status / warnings).
* **Governance surface** — audit logs, model & dataset registries, versions,
  the dashboard aggregation and the search/export contracts.

Everything is optional-by-default so a trace derived from a partial report never
fails validation — governance must observe the system as it is, not reject it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ==========================================================================
# Enums
# ==========================================================================
class DecisionStatus(str, Enum):
    """Terminal status of a traced AI decision."""

    SUCCESS = "success"
    PARTIAL = "partial"        # some stages skipped/degraded but a result exists
    LOW_CONFIDENCE = "low_confidence"
    FAILED = "failed"


class StepStatus(str, Enum):
    """Per-pipeline-step execution status."""

    COMPLETED = "completed"
    WARNING = "warning"
    SKIPPED = "skipped"
    FAILED = "failed"


class ReliabilityBand(str, Enum):
    """Coarse reliability bucket derived from the confidence analysis."""

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNRELIABLE = "unreliable"


class ModelStatus(str, Enum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"


class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"


# ==========================================================================
# Versions
# ==========================================================================
class VersionInfo(BaseModel):
    """The pinned versions stamped onto a trace (from the version manager)."""

    model_version: str = ""
    ocr_model_version: str = ""
    medicine_matcher_version: str = ""
    interaction_model_version: str = ""
    clinical_model_version: str = ""
    dataset_version: str = ""
    prompt_version: str = ""
    pipeline_version: str = ""
    rag_index_version: str = ""


# ==========================================================================
# AI Decision Trace
# ==========================================================================
class TracedMedicine(BaseModel):
    name: str | None = None
    raw_text: str = ""
    confidence: float = 0.0
    dosage: str | None = None
    matched: bool = False
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    """A RAG chunk retained for provenance + explainability."""

    source: str = ""
    text: str = ""
    score: float = 0.0


class DecisionTrace(BaseModel):
    """The complete, reproducible record of one AI decision (Requirement: TRACE)."""

    trace_id: str
    created_at: datetime
    source_report_id: str | None = None

    # Identity (subject to PHI masking on export).
    patient_id: str | None = None
    patient_name: str | None = None

    # Inputs & outputs of each stage.
    ocr_text: str = ""
    ocr_provider: str | None = None
    ocr_confidence: float = 0.0
    medicines: list[TracedMedicine] = Field(default_factory=list)
    disease_prediction: list[dict[str, Any]] = Field(default_factory=list)
    top_disease: str | None = None
    confidence: float = 0.0                              # overall 0..1
    drug_interaction: dict[str, Any] | None = None
    clinical_decision: dict[str, Any] | None = None

    # RAG provenance.
    prompt: str = ""
    rag_documents: list[RetrievedChunk] = Field(default_factory=list)

    final_recommendation: list[str] = Field(default_factory=list)

    # Provenance / reproducibility.
    execution_time: float = 0.0                          # seconds
    status: DecisionStatus = DecisionStatus.SUCCESS
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    versions: VersionInfo = Field(default_factory=VersionInfo)


class DecisionTraceItem(BaseModel):
    """Lightweight row for the decisions list / search results."""

    trace_id: str
    created_at: datetime
    patient_name: str | None = None
    top_disease: str | None = None
    medicine_count: int = 0
    confidence: float = 0.0
    status: DecisionStatus = DecisionStatus.SUCCESS
    execution_time: float = 0.0
    model_version: str = ""
    dataset_version: str = ""


class DecisionPage(BaseModel):
    items: list[DecisionTraceItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 0


# ==========================================================================
# Explainability (Requirement: EXPLAINABILITY)
# ==========================================================================
class ExplanationItem(BaseModel):
    """One "why" — a decision, its rationale and the evidence behind it."""

    subject: str                     # e.g. the medicine / disease / document
    decision: str                    # selected / rejected / flagged
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = None


class ExplanationReport(BaseModel):
    """Every sub-decision of one trace, explained."""

    trace_id: str
    ocr: list[ExplanationItem] = Field(default_factory=list)
    medicine_matching: list[ExplanationItem] = Field(default_factory=list)
    disease_selected: list[ExplanationItem] = Field(default_factory=list)
    disease_rejected: list[ExplanationItem] = Field(default_factory=list)
    drug_interactions: list[ExplanationItem] = Field(default_factory=list)
    rag_retrieval: list[ExplanationItem] = Field(default_factory=list)
    final_recommendation: list[ExplanationItem] = Field(default_factory=list)
    summary: str = ""


# ==========================================================================
# Confidence analysis (Requirement: CONFIDENCE ANALYSIS)
# ==========================================================================
class ConfidenceReport(BaseModel):
    trace_id: str
    confidence: float = 0.0            # 0..1 overall
    reliability: ReliabilityBand = ReliabilityBand.MODERATE
    reliability_score: float = 0.0     # 0..100
    calibration: float = 0.0           # 0..1 — agreement of stage confidences
    evidence_strength: float = 0.0     # 0..1 — RAG + match support
    model_uncertainty: float = 0.0     # 0..1 — spread/entropy proxy
    missing_information: list[str] = Field(default_factory=list)
    drivers: list[str] = Field(default_factory=list)
    summary: str = ""


# ==========================================================================
# Pipeline view (Requirement: AI PIPELINE VIEW)
# ==========================================================================
class PipelineStep(BaseModel):
    key: str
    name: str
    order: int
    status: StepStatus = StepStatus.COMPLETED
    execution_time: float = 0.0        # seconds
    confidence: float | None = None    # 0..1 where meaningful
    warnings: list[str] = Field(default_factory=list)
    detail: str = ""


class PipelineView(BaseModel):
    trace_id: str
    steps: list[PipelineStep] = Field(default_factory=list)
    total_time: float = 0.0
    status: DecisionStatus = DecisionStatus.SUCCESS


# ==========================================================================
# Audit logs (Requirement: AUDIT LOGS)
# ==========================================================================
class AuditLogItem(BaseModel):
    id: int
    created_at: datetime
    user: str = "system"
    method: str = ""
    api: str = ""                      # request path
    status_code: int = 0
    processing_time_ms: float = 0.0
    model_used: str | None = None
    prompt: str | None = None
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class AuditLogPage(BaseModel):
    items: list[AuditLogItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    pages: int = 0


# ==========================================================================
# Model registry (Requirement: MODEL REGISTRY)
# ==========================================================================
class ModelEntry(BaseModel):
    name: str
    version: str
    accuracy: float | None = None      # 0..1
    training_date: str | None = None
    dataset: str | None = None
    status: ModelStatus = ModelStatus.PRODUCTION
    description: str = ""
    updated_at: datetime | None = None


class ModelRegisterRequest(BaseModel):
    name: str
    version: str
    accuracy: float | None = None
    training_date: str | None = None
    dataset: str | None = None
    status: ModelStatus = ModelStatus.PRODUCTION
    description: str = ""


# ==========================================================================
# Dataset registry (Requirement: DATASET REGISTRY)
# ==========================================================================
class DatasetEntry(BaseModel):
    name: str
    version: str
    source: str | None = None
    size: str | None = None            # human-readable ("18,432 rows", "4.2 MB")
    date_added: str | None = None
    purpose: str = ""
    updated_at: datetime | None = None


class DatasetRegisterRequest(BaseModel):
    name: str
    version: str
    source: str | None = None
    size: str | None = None
    date_added: str | None = None
    purpose: str = ""


# ==========================================================================
# Dashboard (Requirement: DASHBOARD)
# ==========================================================================
class NameCount(BaseModel):
    name: str
    count: int


class GovernanceDashboard(BaseModel):
    total_decisions: int = 0
    average_confidence: float = 0.0            # 0..1
    average_processing_time: float = 0.0       # seconds
    failed_predictions: int = 0
    audit_failures: int = 0                    # audit-log entries with errors
    low_confidence_cases: int = 0
    most_common_diseases: list[NameCount] = Field(default_factory=list)
    most_common_medicines: list[NameCount] = Field(default_factory=list)
    status_distribution: dict[str, int] = Field(default_factory=dict)
    decisions_over_time: list[dict[str, Any]] = Field(default_factory=list)
    total_audit_logs: int = 0
    models_registered: int = 0
    datasets_registered: int = 0
    versions: VersionInfo = Field(default_factory=VersionInfo)
    generated_at: datetime | None = None


# ==========================================================================
# Sync / maintenance
# ==========================================================================
class SyncResult(BaseModel):
    imported: int = 0
    skipped: int = 0
    total_traces: int = 0
    took_ms: float = 0.0
    message: str = ""
