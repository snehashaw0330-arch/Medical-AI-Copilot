"""Pydantic models for the Clinical Reasoning Platform (frontend contract).

These types are the *stable* boundary between the reasoning backend and the React
UI. Unlike the Clinical Decision Support module — which returns a flat, graded
report — the reasoning module's whole purpose is to **show its work**. Every
report therefore carries:

* a :class:`ReasoningStep` chain (the ordered pipeline, each stage with a status,
  a human summary and structured detail) so the UI can animate the flow;
* a :class:`ConfidenceBreakdown` (weighted components, not just a number) so a
  clinician can see *why* the platform is (un)certain;
* a list of :class:`DifferentialDiagnosis` with explicit *rejection reasons* for
  the alternatives that were considered and dropped;
* a :class:`ReasoningExplanation` that answers, for the leading diagnosis, the
  nine "why" questions the product requires (which symptoms, which medicines,
  which documents, which rules, what is missing…).

The shape is intentionally framework-agnostic and additive: it reuses the same
four-level ``RiskLevel`` semantics as the rest of the app and never removes or
depends on mutating any existing module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Timezone-aware UTC now (kept local so schemas have no service import)."""
    return datetime.now(timezone.utc)


# ==========================================================================
# Enumerations
# ==========================================================================
class RiskLevel(str, Enum):
    """Four-level clinical risk scale (mirrors clinical_decision.RiskLevel)."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class StepStatus(str, Enum):
    """Lifecycle of a single reasoning step (drives the animated pipeline)."""

    PENDING = "pending"      # not started
    RUNNING = "running"      # in progress (transient; used by streaming clients)
    COMPLETE = "complete"    # finished with a usable result
    SKIPPED = "skipped"      # intentionally not run (feature off / no input)
    FAILED = "failed"        # attempted but errored (best-effort — never fatal)


class ConfidenceLevel(str, Enum):
    """Human bucket for an overall 0-100 confidence score."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class DiagnosisStatus(str, Enum):
    """Where a candidate condition landed in the differential."""

    LEADING = "leading"          # the top-ranked working diagnosis
    CONSIDERED = "considered"    # a plausible alternative kept in view
    REJECTED = "rejected"        # ruled out (carries a rejection_reason)


# ==========================================================================
# Request
# ==========================================================================
class ReasoningRequest(BaseModel):
    """Input for ``POST /reasoning/analyze``.

    Every field is optional so the endpoint can be driven from any context: an
    OCR result (``ocr_text`` + ``medicines``), the disease page (``symptoms``),
    or a manual clinician form. The pipeline degrades gracefully and records
    exactly what was missing in the confidence breakdown.
    """

    medicines: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    disease: str | None = None            # known / already-predicted condition
    diagnosis: str | None = None          # free-text diagnosis (e.g. from OCR)
    ocr_text: str | None = None           # raw OCR text, echoed into OCR findings
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = None             # "male" | "female" | "other"

    include_rag: bool = True              # retrieve knowledge-base evidence
    run_disease_prediction: bool = True   # predict from symptoms if no disease
    top_k: int | None = Field(default=None, ge=1, le=10)
    use_cache: bool = True                # serve identical re-runs from cache
    source_record_id: str | None = None   # optional link to an OCR history record


# ==========================================================================
# Building blocks
# ==========================================================================
class SymptomContribution(BaseModel):
    """How much one reported symptom pushed toward the leading diagnosis."""

    symptom: str
    weight: float = 0.0                   # 0..1 normalised contribution
    matched: bool = True                  # recognised by the disease model?
    note: str = ""


class MedicineInsight(BaseModel):
    """One medicine and the role it played in the reasoning."""

    name: str                             # name as supplied
    resolved_name: str | None = None      # canonical name if matched to the KB
    matched: bool = False                 # resolved against the medicine dataset?
    role: str = "treatment"               # "treatment" | "risk" | "interacting"
    influence: str = ""                   # plain-language influence on the decision


class EvidenceCard(BaseModel):
    """A single retrieved knowledge-base document used as clinical evidence."""

    id: str
    title: str
    source: str = ""                      # document / file the snippet came from
    snippet: str = ""                     # the retrieved passage
    relevance: float = 0.0                # 0..1 retrieval score
    used_for: str = ""                    # what this evidence supported


class MatchedRule(BaseModel):
    """A deterministic clinical rule that fired for this case."""

    id: str
    name: str
    category: str = "clinical"            # "interaction" | "age" | "red-flag" | …
    severity: RiskLevel = RiskLevel.MODERATE
    rationale: str = ""                   # why it fired
    triggered_by: list[str] = Field(default_factory=list)  # inputs that matched


class DifferentialDiagnosis(BaseModel):
    """One candidate condition in the differential, with supporting/against evidence."""

    disease: str
    confidence: float = 0.0               # 0..100
    status: DiagnosisStatus = DiagnosisStatus.CONSIDERED
    supporting: list[str] = Field(default_factory=list)   # symptoms/facts for it
    against: list[str] = Field(default_factory=list)      # facts against it
    rejection_reason: str = ""            # populated when status == rejected
    source: str = "model"                 # "model" | "input" | "diagnosis"


class ConfidenceComponent(BaseModel):
    """One weighted contributor to the overall confidence score."""

    name: str
    weight: float = 0.0                   # 0..1, weights sum to ~1 across components
    score: float = 0.0                    # 0..100 for this component alone
    contribution: float = 0.0             # weight * score, the points it added
    note: str = ""


class ConfidenceBreakdown(BaseModel):
    """The full, auditable confidence calculation."""

    overall: float = 0.0                  # 0..100 weighted total
    level: ConfidenceLevel = ConfidenceLevel.LOW
    components: list[ConfidenceComponent] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    rationale: str = ""


class ReasoningStep(BaseModel):
    """One stage of the reasoning pipeline (the animated flow renders these)."""

    order: int
    key: str                              # stable id, e.g. "disease_prediction"
    name: str                             # display name
    status: StepStatus = StepStatus.PENDING
    title: str = ""                       # one-line headline result
    summary: str = ""                     # human explanation of what happened
    detail: dict = Field(default_factory=dict)   # structured payload for the UI
    duration_ms: float = 0.0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Recommendation(BaseModel):
    """A single clinical recommendation with its own rationale (Requirement)."""

    title: str
    detail: str = ""
    priority: RiskLevel = RiskLevel.MODERATE
    category: str = "management"          # "management" | "monitoring" | "referral"
    rationale: str = ""                   # why the platform suggests it


class FollowUp(BaseModel):
    """A follow-up / safety-net suggestion."""

    action: str
    timeframe: str = ""                   # e.g. "within 48 hours", "2 weeks"
    reason: str = ""


class MedicalReference(BaseModel):
    """A citation surfaced in the report's references section."""

    label: str
    source: str = ""
    detail: str = ""


# ==========================================================================
# The nine-part explanation of the leading recommendation
# ==========================================================================
class ReasoningExplanation(BaseModel):
    """Answers the required "why" questions for the leading diagnosis.

    Every field maps directly to one of the product's explainability
    requirements, so the UI can render them as labelled sections.
    """

    why_disease: str = ""                                  # why predicted
    contributing_symptoms: list[SymptomContribution] = Field(default_factory=list)
    influencing_medicines: list[MedicineInsight] = Field(default_factory=list)
    rag_documents_used: list[EvidenceCard] = Field(default_factory=list)
    matched_rules: list[MatchedRule] = Field(default_factory=list)
    alternatives_considered: list[DifferentialDiagnosis] = Field(default_factory=list)
    rejected_alternatives: list[DifferentialDiagnosis] = Field(default_factory=list)
    confidence_breakdown: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    missing_information: list[str] = Field(default_factory=list)


# ==========================================================================
# Report sub-sections (one model per Clinical Reasoning Report section)
# ==========================================================================
class PatientSummary(BaseModel):
    age: int | None = None
    gender: str | None = None
    symptom_count: int = 0
    medicine_count: int = 0
    narrative: str = ""


class OCRFindings(BaseModel):
    raw_text: str | None = None
    detected_medicines: list[str] = Field(default_factory=list)
    diagnosis: str | None = None
    note: str = ""


class MedicineAnalysis(BaseModel):
    insights: list[MedicineInsight] = Field(default_factory=list)
    resolved: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    note: str = ""


class DiseasePredictionSection(BaseModel):
    leading: DifferentialDiagnosis | None = None
    hypotheses: list[DifferentialDiagnosis] = Field(default_factory=list)
    method: str = ""                      # how the leading diagnosis was derived


class ConfidenceAnalysisSection(BaseModel):
    breakdown: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)


# ==========================================================================
# Full report (the frontend contract)
# ==========================================================================
class ClinicalReasoningReport(BaseModel):
    """Complete Clinical Reasoning Report with every required section."""

    id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    cached: bool = False                  # served from cache?
    duration_ms: float = 0.0              # wall-clock of the whole pipeline

    # --- Report sections --------------------------------------------------
    patient_summary: PatientSummary = Field(default_factory=PatientSummary)
    ocr_findings: OCRFindings = Field(default_factory=OCRFindings)
    medicine_analysis: MedicineAnalysis = Field(default_factory=MedicineAnalysis)
    disease_prediction: DiseasePredictionSection = Field(default_factory=DiseasePredictionSection)
    clinical_evidence: list[EvidenceCard] = Field(default_factory=list)
    reasoning_chain: list[ReasoningStep] = Field(default_factory=list)
    drug_interaction_analysis: dict | None = None   # reused InteractionReport shape
    confidence_analysis: ConfidenceAnalysisSection = Field(default_factory=ConfidenceAnalysisSection)
    alternative_diagnoses: list[DifferentialDiagnosis] = Field(default_factory=list)
    clinical_recommendations: list[Recommendation] = Field(default_factory=list)
    follow_up_suggestions: list[FollowUp] = Field(default_factory=list)
    medical_references: list[MedicalReference] = Field(default_factory=list)

    # --- Cross-cutting explainability + grading ---------------------------
    explanation: ReasoningExplanation = Field(default_factory=ReasoningExplanation)
    matched_rules: list[MatchedRule] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    confidence: float = 0.0               # 0..100 (mirrors confidence_analysis.overall)

    warnings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    provider: str = "clinical-reasoning-engine"
    disclaimer: str = (
        "This AI clinical reasoning is an educational decision-support aid only "
        "and is NOT a medical diagnosis or a substitute for professional "
        "judgement. Every step, score and recommendation must be verified by a "
        "qualified clinician before any treatment decision. In an emergency, "
        "seek urgent care."
    )


# ==========================================================================
# History (list + detail) + dashboard stats
# ==========================================================================
class ReasoningHistoryItem(BaseModel):
    """Lightweight row for the reasoning-history list view."""

    id: str
    created_at: datetime
    leading_disease: str | None = None
    medicine_count: int = 0
    symptom_count: int = 0
    risk_level: RiskLevel = RiskLevel.LOW
    confidence: float = 0.0
    step_count: int = 0


class ReasoningHistoryPage(BaseModel):
    items: list[ReasoningHistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0


class ReasoningStats(BaseModel):
    total_reports: int = 0
    average_confidence: float = 0.0
    critical_cases: int = 0
    high_risk_cases: int = 0
    cache_hits: int = 0
    cache_size: int = 0
