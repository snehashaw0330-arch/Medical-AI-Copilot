"""Pydantic models for the Symptom Checker & Triage API (frontend contract).

These types are the *stable* boundary between the backend and the React UI. A
:class:`TriageAssessment` is assembled by the service from several sources — the
categorized symptom catalog, the existing disease-prediction model, the
deterministic triage engine and the RAG knowledge base — but the shape the UI
consumes is intentionally simple and framework-agnostic.

The four-level :class:`UrgencyLevel` scale (self_care / visit_clinic /
urgent_care / emergency) maps cleanly onto the frontend badge tones, mirroring
the pattern already used by the clinical-decision and drug-interaction modules.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    """How severe the overall presentation is judged to be."""

    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class UrgencyLevel(str, Enum):
    """Four-level triage urgency scale (Requirement 5)."""

    SELF_CARE = "self_care"
    VISIT_CLINIC = "visit_clinic"
    URGENT_CARE = "urgent_care"
    EMERGENCY = "emergency"


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class SymptomAnalysisRequest(BaseModel):
    """Input for ``POST /symptoms/analyze``.

    ``symptoms`` may be typed free-text or picked from the categorized catalog —
    both are resolved by the same matcher. ``severity`` is the 1–10 slider value
    and ``duration`` is one of the catalog duration keys (see
    :data:`symptom_matcher.DURATIONS`); both are optional and degrade gracefully.
    """

    symptoms: list[str] = Field(default_factory=list)
    severity: int = Field(default=5, ge=1, le=10)   # UI slider, 1 (mild)–10 (severe)
    duration: str | None = None                     # catalog duration key
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = None                       # "male" | "female" | "other"

    include_rag: bool = True                         # evidence-based explanation
    top_k: int = Field(default=5, ge=1, le=10)       # number of conditions to return
    persist: bool = True                             # save this assessment to history


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
class ConditionHypothesis(BaseModel):
    """One possible condition with its confidence and reasoning (Requirement 4)."""

    disease: str
    confidence: float = 0.0                # 0..100, from the ML model
    explanation: str = ""                  # human-readable "why"
    matched_symptoms: list[str] = []       # reported symptoms typical for it
    source: str = "disease-model"


class RedFlag(BaseModel):
    """A symptom that warrants escalated attention (Requirement 4)."""

    symptom: str
    reason: str
    emergency: bool = False                # True → contributes to an EMERGENCY grade


class SymptomResolution(BaseModel):
    """How one input symptom was resolved against the known catalog."""

    input: str
    matched: str | None = None
    category: str | None = None
    score: float = 0.0                     # 0..100 match score


class RelatedDocument(BaseModel):
    """A knowledge-base passage retrieved by RAG (Requirement 10)."""

    source: str
    excerpt: str = ""
    score: float = 0.0


# --------------------------------------------------------------------------
# Full assessment
# --------------------------------------------------------------------------
class TriageAssessment(BaseModel):
    """Complete symptom-checker & triage report (the frontend contract)."""

    id: str | None = None
    created_at: datetime | None = None

    # --- Inputs, echoed back for the report header ------------------------
    symptoms: list[str] = []               # resolved canonical symptom names
    resolved_symptoms: list[SymptomResolution] = []
    unmatched_symptoms: list[str] = []
    severity_input: int = 5
    duration: str | None = None
    age: int | None = None
    gender: str | None = None

    # --- Core outputs (Requirement 4) -------------------------------------
    possible_conditions: list[ConditionHypothesis] = []
    confidence_level: str = "low"          # high | moderate | low (from the model)
    severity_level: SeverityLevel = SeverityLevel.MILD
    urgency_level: UrgencyLevel = UrgencyLevel.SELF_CARE
    urgency_label: str = "Self Care"
    urgency_description: str = ""
    triage_score: float = 0.0              # 0..100, higher = more urgent
    recommended_specialist: str = "General Physician"
    recommended_tests: list[str] = []
    home_care: list[str] = []
    red_flags: list[RedFlag] = []
    emergency_warning: str | None = None   # set when an emergency is detected

    # --- Evidence (Requirement 6 & 10) ------------------------------------
    rag_explanation: str | None = None     # RAG narrative (best-effort)
    related_documents: list[RelatedDocument] = []
    rag_sources: list[str] = []

    warnings: list[str] = []
    sources: list[str] = []                # provenance (model / rag / rules)
    provider: str = "symptom-triage-engine"
    disclaimer: str = (
        "This automated symptom checker is an educational triage aid only and is "
        "NOT a medical diagnosis or a substitute for professional judgement. If "
        "you think this may be an emergency, call your local emergency number or "
        "go to the nearest emergency department immediately."
    )


# --------------------------------------------------------------------------
# Symptom catalog (Requirements 2 & 3)
# --------------------------------------------------------------------------
class SymptomCategory(BaseModel):
    """One named group of selectable symptoms."""

    key: str                               # machine key, e.g. "respiratory"
    label: str                             # display name, e.g. "Respiratory"
    symptoms: list[str] = []               # canonical symptom names in this group


class DurationOption(BaseModel):
    """A selectable duration bucket for the frontend selector."""

    key: str
    label: str


class SymptomCatalog(BaseModel):
    """Everything the UI needs to build the symptom picker + duration selector."""

    categories: list[SymptomCategory] = []
    durations: list[DurationOption] = []
    total_symptoms: int = 0


# --------------------------------------------------------------------------
# History (list + detail)
# --------------------------------------------------------------------------
class TriageHistoryItem(BaseModel):
    """Lightweight row for the assessment-history list view."""

    id: str
    created_at: datetime
    symptoms: list[str] = []
    symptom_count: int = 0
    top_condition: str | None = None
    urgency_level: UrgencyLevel = UrgencyLevel.SELF_CARE
    severity_level: SeverityLevel = SeverityLevel.MILD
    triage_score: float = 0.0


class TriageHistoryPage(BaseModel):
    """A page of history items plus pagination metadata."""

    items: list[TriageHistoryItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
