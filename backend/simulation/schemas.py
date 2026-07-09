"""Pydantic models for the AI Medical Simulation Engine (frontend contract).

The Simulation Engine answers "what if?": a clinician takes a baseline
prescription + patient and describes one or more **scenarios** (dose changes,
replace/remove/add a medicine, or patient changes such as age / weight /
pregnancy / renal or hepatic impairment / allergies). For each scenario the engine
projects the resulting drug interactions, disease risk, clinical recommendations,
treatment suggestions, side effects, contraindications and RAG evidence — with a
confidence breakdown — and compares every variant against the baseline.

These types are the stable boundary to the React "Treatment Simulator" page. The
module is purely additive: it only *reads* from the existing subsystems (OCR,
disease, drug-interactions, clinical-decision, RAG, reports) and mutates none.
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
class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeAction(str, Enum):
    """One treatment edit a clinician can simulate."""

    DOSAGE = "dosage_change"     # change the dose of an existing medicine
    REPLACE = "replace"          # swap one medicine for another
    REMOVE = "remove"            # stop a medicine
    ADD = "add"                  # start a new medicine


class Organ(str, Enum):
    """Severity grade for renal / hepatic impairment."""

    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


# ==========================================================================
# Building blocks
# ==========================================================================
class MedicineItem(BaseModel):
    """A single prescribed medicine (parsed name + dose)."""

    name: str
    dose: float | None = None
    unit: str = "mg"
    frequency: str | None = None
    raw: str = ""                        # original free-text, if any

    def label(self) -> str:
        parts = [self.name]
        if self.dose is not None:
            parts.append(f"{self.dose:g}{self.unit}")
        if self.frequency:
            parts.append(self.frequency)
        return " ".join(parts)


class PatientState(BaseModel):
    """The patient the simulation is run for (baseline or effective)."""

    age: int | None = Field(default=None, ge=0, le=120)
    weight_kg: float | None = Field(default=None, ge=0, le=400)
    gender: str | None = None
    pregnant: bool = False
    renal_disease: Organ = Organ.NONE
    hepatic_disease: Organ = Organ.NONE
    allergies: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class MedicineChange(BaseModel):
    """One medicine edit within a scenario."""

    action: ChangeAction
    target: str | None = None            # existing medicine (dosage/replace/remove)
    name: str | None = None              # new medicine (add / replacement)
    dose: float | None = None
    unit: str | None = None
    frequency: str | None = None


class PatientChange(BaseModel):
    """Patient-side overrides applied within a scenario (all optional)."""

    age: int | None = Field(default=None, ge=0, le=120)
    weight_kg: float | None = Field(default=None, ge=0, le=400)
    pregnant: bool | None = None
    renal_disease: Organ | None = None
    hepatic_disease: Organ | None = None
    allergies_add: list[str] = Field(default_factory=list)
    allergies_remove: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    """A named set of changes to simulate against the baseline."""

    id: str | None = None
    name: str = "Scenario"
    medicine_changes: list[MedicineChange] = Field(default_factory=list)
    patient_changes: PatientChange | None = None


# ==========================================================================
# Request
# ==========================================================================
class SimulationRequest(BaseModel):
    """Input for ``POST /simulation/run``.

    ``baseline_medicines`` may be supplied as objects or as plain strings (which
    are parsed). ``scenarios`` describe the "what-if" edits; an implicit baseline
    (no changes) is always simulated so every scenario can be compared to it.
    """

    baseline_medicines: list[MedicineItem] = Field(default_factory=list)
    patient: PatientState = Field(default_factory=PatientState)
    scenarios: list[Scenario] = Field(default_factory=list)

    include_rag: bool = True
    persist: bool = True
    use_cache: bool = True
    generate_report: bool = False        # also persist a Medical Report for the best scenario
    source_record_id: str | None = None  # link to an OCR history record


# ==========================================================================
# Sub-results
# ==========================================================================
class DiseaseHypothesis(BaseModel):
    disease: str
    confidence: float = 0.0
    matched_symptoms: list[str] = Field(default_factory=list)
    explanation: str = ""


class DiseaseRisk(BaseModel):
    level: RiskLevel = RiskLevel.LOW
    score: float = 0.0                   # 0..100
    hypotheses: list[DiseaseHypothesis] = Field(default_factory=list)
    modifiers: list[str] = Field(default_factory=list)   # patient factors raising risk


class SideEffect(BaseModel):
    medicine: str
    effect: str
    likelihood: str = "possible"         # "common" | "possible" | "rare"


class Contraindication(BaseModel):
    medicine: str
    reason: str
    severity: RiskLevel = RiskLevel.HIGH
    factor: str = ""                     # "pregnancy" | "renal" | "allergy" | ...


class Recommendation(BaseModel):
    title: str
    detail: str = ""
    priority: RiskLevel = RiskLevel.MODERATE
    rationale: str = ""


class TreatmentSuggestion(BaseModel):
    suggestion: str
    rationale: str = ""
    caution: str = ""


class EvidenceCard(BaseModel):
    id: str
    title: str
    source: str = ""
    snippet: str = ""
    relevance: float = 0.0


class ConfidenceComponent(BaseModel):
    name: str
    weight: float = 0.0
    score: float = 0.0
    contribution: float = 0.0
    note: str = ""


class ConfidenceBreakdown(BaseModel):
    overall: float = 0.0
    level: str = "low"
    components: list[ConfidenceComponent] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    rationale: str = ""


# ==========================================================================
# One scenario's result
# ==========================================================================
class ScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    is_baseline: bool = False

    resulting_medicines: list[MedicineItem] = Field(default_factory=list)
    applied_changes: list[str] = Field(default_factory=list)   # human-readable
    effective_patient: PatientState = Field(default_factory=PatientState)

    drug_interactions: dict | None = None
    disease_risk: DiseaseRisk = Field(default_factory=DiseaseRisk)
    clinical_recommendations: list[Recommendation] = Field(default_factory=list)
    treatment_suggestions: list[TreatmentSuggestion] = Field(default_factory=list)
    side_effects: list[SideEffect] = Field(default_factory=list)
    contraindications: list[Contraindication] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)

    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    risk_level: RiskLevel = RiskLevel.LOW
    risk_score: float = 0.0              # composite 0..100 (lower is safer)
    report_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


# ==========================================================================
# Comparison of a variant against the baseline (or A vs B)
# ==========================================================================
class ComparisonDelta(BaseModel):
    from_scenario_id: str
    from_scenario_name: str
    to_scenario_id: str
    to_scenario_name: str

    risk_score_delta: float = 0.0        # to - from (negative == safer)
    confidence_delta: float = 0.0
    interaction_count_delta: int = 0
    new_interactions: list[str] = Field(default_factory=list)
    resolved_interactions: list[str] = Field(default_factory=list)
    added_medicines: list[str] = Field(default_factory=list)
    removed_medicines: list[str] = Field(default_factory=list)
    new_contraindications: list[str] = Field(default_factory=list)
    verdict: str = ""                    # plain-language summary
    safer: bool = False


# ==========================================================================
# Full report (result of POST /simulation/run)
# ==========================================================================
class SimulationReport(BaseModel):
    id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    cached: bool = False
    duration_ms: float = 0.0

    baseline: ScenarioResult
    results: list[ScenarioResult] = Field(default_factory=list)   # variant scenarios
    comparisons: list[ComparisonDelta] = Field(default_factory=list)
    recommended_scenario_id: str | None = None
    summary: str = ""

    warnings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    provider: str = "simulation-engine"
    disclaimer: str = (
        "This AI treatment simulation is an educational decision-support aid only "
        "and is NOT a medical order or a substitute for professional judgement. "
        "Projected interactions, risks and suggestions must be verified by a "
        "qualified clinician before any treatment change. In an emergency, seek "
        "urgent care."
    )


# ==========================================================================
# History (list + detail)
# ==========================================================================
class SimulationHistoryItem(BaseModel):
    id: str
    created_at: datetime
    medicine_count: int = 0
    scenario_count: int = 0
    top_disease: str | None = None
    baseline_risk: RiskLevel = RiskLevel.LOW
    best_scenario: str | None = None
    summary: str = ""


class SimulationHistoryPage(BaseModel):
    items: list[SimulationHistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
