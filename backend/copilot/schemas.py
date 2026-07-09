"""Pydantic models for the AI Medical Copilot Workspace (frontend contract).

These types are the stable boundary between the Copilot backend and the React
workspace. The Copilot is a *session-scoped orchestrator*: it chains every
existing module together, remembers the current patient for the session, and
records everything it did as an activity timeline + reasoning trace.

Nothing here removes or depends on mutating any existing module — the Copilot
only *reads* from the other subsystems and assembles their outputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================================================
# Enumerations
# ==========================================================================
class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    SKIPPED = "skipped"
    FAILED = "failed"


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ==========================================================================
# Reasoning + activity
# ==========================================================================
class ReasoningStep(BaseModel):
    """One stage of the Copilot workflow (mirrors the 11-step pipeline)."""

    order: int
    key: str
    name: str
    status: StepStatus = StepStatus.PENDING
    title: str = ""
    summary: str = ""
    detail: dict = Field(default_factory=dict)
    duration_ms: float = 0.0
    at: datetime | None = None


class ActivityEvent(BaseModel):
    """A single entry in the AI Activity Timeline (e.g. '09:42 OCR Completed')."""

    at: datetime = Field(default_factory=utcnow)
    label: str                              # "OCR Completed", "Medicines Found", …
    detail: str = ""
    status: StepStatus = StepStatus.COMPLETE
    step_key: str = ""


# ==========================================================================
# Patient context (remembered for the session)
# ==========================================================================
class ReportRef(BaseModel):
    """Lightweight pointer to a previously-generated analysis/report."""

    analysis_id: str
    report_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    title: str = ""
    leading_disease: str | None = None
    medicine_count: int = 0
    risk_level: str = "low"


class PatientContext(BaseModel):
    """The evolving, session-scoped picture of the current patient."""

    session_id: str
    patient_name: str | None = None
    age: int | None = None
    gender: str | None = None
    current_medicines: list[str] = Field(default_factory=list)
    known_conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    previous_reports: list[ReportRef] = Field(default_factory=list)
    timeline: list[ActivityEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    analysis_count: int = 0


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    at: datetime = Field(default_factory=utcnow)
    references: list[str] = Field(default_factory=list)


# ==========================================================================
# Requests
# ==========================================================================
class CopilotAnalyzeRequest(BaseModel):
    """JSON body for ``POST /copilot/analyze`` when no file is uploaded.

    The endpoint also accepts a multipart form (file + these fields); this model
    documents the shape for the file-less / manual path.
    """

    session_id: str | None = None
    text: str | None = None                 # raw prescription / clinical text
    medicines: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    patient_name: str | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = None
    diagnosis: str | None = None
    include_rag: bool = True
    use_cache: bool = True


class CopilotChatRequest(BaseModel):
    session_id: str
    message: str


# ==========================================================================
# Sub-results (each maps to one workflow stage / one right-panel widget)
# ==========================================================================
class OCRSummary(BaseModel):
    provider: str = ""
    raw_text: str = ""
    detected_medicines: list[str] = Field(default_factory=list)
    fields: dict = Field(default_factory=dict)
    overall_confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class DiseaseHypothesis(BaseModel):
    disease: str
    confidence: float = 0.0
    matched_symptoms: list[str] = Field(default_factory=list)
    explanation: str = ""


class EvidenceCard(BaseModel):
    id: str
    title: str
    source: str = ""
    snippet: str = ""
    relevance: float = 0.0


class Recommendation(BaseModel):
    title: str
    detail: str = ""
    priority: str = "moderate"
    rationale: str = ""


class TreatmentSuggestion(BaseModel):
    suggestion: str
    rationale: str = ""
    caution: str = ""


class FollowUpSuggestion(BaseModel):
    action: str
    timeframe: str = ""
    reason: str = ""


class MedicalReference(BaseModel):
    label: str
    source: str = ""
    detail: str = ""


# ==========================================================================
# The full Copilot analysis (result of POST /copilot/analyze)
# ==========================================================================
class CopilotAnalysis(BaseModel):
    analysis_id: str
    session_id: str
    created_at: datetime = Field(default_factory=utcnow)
    cached: bool = False
    duration_ms: float = 0.0

    # Per-stage outputs -----------------------------------------------------
    ocr: OCRSummary | None = None
    medicines: list[str] = Field(default_factory=list)
    drug_interactions: dict | None = None
    disease_prediction: list[DiseaseHypothesis] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)
    clinical_decision: dict | None = None

    # AI narratives ---------------------------------------------------------
    summary: str = ""
    treatment_suggestions: list[TreatmentSuggestion] = Field(default_factory=list)
    follow_up_suggestions: list[FollowUpSuggestion] = Field(default_factory=list)

    # Roll-ups shown in the right panel ------------------------------------
    recommendations: list[Recommendation] = Field(default_factory=list)
    references: list[MedicalReference] = Field(default_factory=list)
    confidence: float = 0.0
    risk_level: str = "low"
    report_id: str | None = None

    # Trace -----------------------------------------------------------------
    reasoning: list[ReasoningStep] = Field(default_factory=list)
    activity: list[ActivityEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    disclaimer: str = (
        "This AI Medical Copilot is an educational decision-support aid only and "
        "is NOT a medical diagnosis or a substitute for professional judgement. "
        "Every finding, summary and suggestion must be verified by a qualified "
        "clinician before any treatment decision. In an emergency, seek urgent care."
    )


# ==========================================================================
# Chat + context + history responses
# ==========================================================================
class CopilotChatResponse(BaseModel):
    session_id: str
    reply: str
    references: list[str] = Field(default_factory=list)
    reasoning: str = ""
    provider: str = ""
    at: datetime = Field(default_factory=utcnow)


class CopilotContextResponse(BaseModel):
    context: PatientContext
    messages: list[ChatMessage] = Field(default_factory=list)
    last_analysis: CopilotAnalysis | None = None
    llm: dict = Field(default_factory=dict)


class CopilotHistoryItem(BaseModel):
    analysis_id: str
    created_at: datetime
    title: str = ""
    leading_disease: str | None = None
    medicine_count: int = 0
    risk_level: str = "low"
    confidence: float = 0.0
    report_id: str | None = None


class CopilotHistoryResponse(BaseModel):
    session_id: str
    items: list[CopilotHistoryItem] = Field(default_factory=list)
    total: int = 0
