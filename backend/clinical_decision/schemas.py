"""Pydantic models for the Clinical Decision Support API (frontend contract).

These types are the *stable* boundary between the backend and the React UI. A
:class:`ClinicalReport` is assembled by the service from several sources — OCR
medicines, disease prediction, drug-interaction analysis, the RAG knowledge base
and the deterministic clinical rules engine — but the shape the UI consumes is
intentionally simple and framework-agnostic.

The four-level :class:`RiskLevel` scale (low / moderate / high / critical) maps
cleanly onto the frontend badge tones (primary / warning / danger / danger),
mirroring the pattern already used by the drug-interaction module.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Four-level clinical risk scale (ordering matters — see risk_analyzer)."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class ClinicalAnalysisRequest(BaseModel):
    """Input for ``POST /clinical/analyze``.

    Every field is optional so the endpoint can be driven from many contexts:
    straight from an OCR result (medicines + parsed patient fields), from the
    disease-prediction page (symptoms), or from a manual clinician form. The
    service degrades gracefully when information is missing and reports exactly
    what was absent in ``missing_information``.
    """

    medicines: list[str] = Field(default_factory=list)   # OCR'd / typed names
    symptoms: list[str] = Field(default_factory=list)     # patient symptoms
    disease: str | None = None            # known / already-predicted condition
    diagnosis: str | None = None          # free-text diagnosis (e.g. from OCR)
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = None             # "male" | "female" | "other"

    include_rag: bool = True              # enrich with knowledge-base context
    run_disease_prediction: bool = True   # predict from symptoms if no disease
    persist: bool = True                  # save this analysis to history
    source_record_id: str | None = None   # optional link to an OCR history record


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
class RedFlag(BaseModel):
    """An urgent clinical alert that warrants immediate attention."""

    title: str
    detail: str = ""
    severity: RiskLevel = RiskLevel.HIGH
    category: str = "clinical"            # "symptom" | "drug" | "age" | ...


class DiseaseHypothesis(BaseModel):
    """One candidate condition (from the disease-prediction model or the input)."""

    disease: str
    confidence: float = 0.0               # 0..100
    explanation: str = ""
    source: str = "model"                 # "model" | "input" | "diagnosis"


# --------------------------------------------------------------------------
# Full report
# --------------------------------------------------------------------------
class ClinicalReport(BaseModel):
    """Complete clinical decision-support report (the frontend contract)."""

    id: str | None = None
    created_at: datetime | None = None

    # --- Inputs, echoed back for the report header ------------------------
    medicines: list[str] = []             # names as analysed
    resolved_medicines: list[str] = []    # canonical names matched to the KB
    unmatched_medicines: list[str] = []   # names we could not resolve
    symptoms: list[str] = []
    age: int | None = None
    gender: str | None = None

    # --- Core clinical outputs (Requirement 3) ----------------------------
    clinical_summary: str = ""
    disease_prediction: list[DiseaseHypothesis] = []
    possible_risks: list[str] = []
    red_flags: list[RedFlag] = []
    contraindications: list[str] = []
    missing_information: list[str] = []
    recommended_next_steps: list[str] = []
    recommended_lab_tests: list[str] = []
    follow_up: list[str] = []

    # Full drug-interaction sub-report (the existing InteractionReport shape,
    # serialised). Reused verbatim so the UI can render the same component.
    drug_interactions: dict[str, Any] | None = None

    # --- Risk + provenance ------------------------------------------------
    risk_level: RiskLevel = RiskLevel.LOW
    risk_score: float = 0.0               # 0..100
    risk_counts: dict[str, int] = {}      # red-flag tally per severity (badges)
    confidence: float = 0.0               # 0..100, how complete/grounded this is
    sources: list[str] = []               # provenance: rules, dataset, rag, model

    # --- Optional RAG narrative -------------------------------------------
    rag_notes: str | None = None
    rag_sources: list[str] = []

    warnings: list[str] = []
    provider: str = "clinical-rules-engine"
    disclaimer: str = (
        "This automated clinical decision support is an educational aid only "
        "and is NOT a medical diagnosis or a substitute for professional "
        "judgement. All findings must be verified by a qualified clinician "
        "before any treatment decision. In an emergency, seek urgent care."
    )


# --------------------------------------------------------------------------
# History (list + detail) + dashboard stats
# --------------------------------------------------------------------------
class ClinicalHistoryItem(BaseModel):
    """Lightweight row for the clinical-history list view."""

    id: str
    created_at: datetime
    medicines: list[str] = []
    medicine_count: int = 0
    top_disease: str | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    risk_score: float = 0.0
    red_flag_count: int = 0
    summary: str = ""


class ClinicalHistoryPage(BaseModel):
    """A page of history items plus pagination metadata."""

    items: list[ClinicalHistoryItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0


class ClinicalStats(BaseModel):
    """Aggregate statistics for the dashboard cards (Requirement 8)."""

    total_reports: int = 0
    critical_cases: int = 0
    high_risk_cases: int = 0
    moderate_risk_cases: int = 0
    low_risk_cases: int = 0
    average_risk_score: float = 0.0
