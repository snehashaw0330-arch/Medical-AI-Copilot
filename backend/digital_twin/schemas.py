"""Pydantic contracts for the Digital Twin API (the frontend contract).

A *Digital Twin* is a continuously-evolving virtual health profile assembled from
everything the platform already knows about a patient — every OCR analysis,
disease prediction, medicine, drug-interaction check, clinical decision and
generated report. These types are the stable boundary the React Digital Twin page
consumes: a health score, a risk assessment, trend series (for charts), a
timeline, medicine/disease history and RAG-backed recommendations.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TrendDirection(str, Enum):
    """Direction of a tracked metric over time."""

    IMPROVING = "improving"
    STABLE = "stable"
    WORSENING = "worsening"


class RiskLevel(str, Enum):
    """Four-level future-risk scale."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
class SeriesPoint(BaseModel):
    """One point on a time-series chart."""

    timestamp: datetime
    value: float
    label: str | None = None


class TrendResult(BaseModel):
    """A tracked metric: its direction, its change, and the series for charting."""

    metric: str                         # e.g. "health_score", "ocr_quality"
    direction: TrendDirection = TrendDirection.STABLE
    delta: float = 0.0                  # change from first to latest point
    higher_is_better: bool = True       # polarity (for colouring in the UI)
    series: list[SeriesPoint] = []
    summary: str = ""


class HealthScoreBreakdown(BaseModel):
    """The six factor sub-scores (0..100) behind the overall health score."""

    adherence: float = 0.0
    risk: float = 0.0
    disease_progression: float = 0.0
    drug_interactions: float = 0.0
    prediction_confidence: float = 0.0
    clinical_warnings: float = 0.0
    weights: dict[str, float] = {}


class RiskAssessment(BaseModel):
    """The predicted future-risk level with the drivers behind it."""

    level: RiskLevel = RiskLevel.LOW
    score: float = 0.0                  # 0..100, higher = more risk
    drivers: list[str] = []             # human-readable reasons
    summary: str = ""


class Prediction(BaseModel):
    """A short-horizon forecast of where the patient is heading."""

    projected_health_score: float | None = None
    projected_risk: RiskLevel | None = None
    direction: TrendDirection = TrendDirection.STABLE
    horizon: str = "next visit"
    confidence: float = 0.0             # 0..1, how much history backs the forecast
    summary: str = ""


class TimelineEvent(BaseModel):
    """One chronological event in the patient's health journey."""

    id: str
    timestamp: datetime
    type: str                           # "report" | "high_risk" | "new_medicine" | ...
    title: str
    description: str = ""
    risk_level: str | None = None
    confidence: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class MedicineHistoryItem(BaseModel):
    """A medicine seen across the patient's history."""

    name: str
    occurrences: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    last_dosage: str | None = None
    status: str = "active"              # "active" (in latest report) | "past"


class DiseaseHistoryItem(BaseModel):
    """A condition seen across the patient's history."""

    disease: str
    occurrences: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class ClinicalDecisionItem(BaseModel):
    """A clinical-decision snapshot from one encounter."""

    timestamp: datetime
    risk_level: str | None = None
    summary: str = ""
    red_flag_count: int = 0
    report_id: str | None = None


class InteractionSummary(BaseModel):
    """Aggregate view of drug interactions across the history."""

    total_flagged: int = 0
    highest_risk: str = "none"
    recent: list[dict[str, Any]] = []


class ReportRef(BaseModel):
    """A lightweight reference to a source report (encounter)."""

    id: str
    created_at: datetime
    top_disease: str | None = None
    risk_level: str | None = None
    medicine_count: int = 0
    confidence: float = 0.0


class EvidenceItem(BaseModel):
    """A RAG knowledge-base passage backing the recommendations."""

    source: str
    text: str = ""


# --------------------------------------------------------------------------
# The Digital Twin
# --------------------------------------------------------------------------
class DigitalTwin(BaseModel):
    """The complete virtual health profile for one patient."""

    patient_id: str
    patient_name: str
    generated_at: datetime | None = None
    report_count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    # Headline
    health_score: float = 0.0                       # 0..100
    health_status: TrendDirection = TrendDirection.STABLE
    health_score_breakdown: HealthScoreBreakdown = HealthScoreBreakdown()
    risk: RiskAssessment = RiskAssessment()
    prediction: Prediction = Prediction()

    # Trends (for the charts)
    trends: dict[str, TrendResult] = {}             # health_score, disease, medicine, ocr_quality, risk

    # Aggregated history
    timeline: list[TimelineEvent] = []
    medicines: list[MedicineHistoryItem] = []
    diseases: list[DiseaseHistoryItem] = []
    clinical_decisions: list[ClinicalDecisionItem] = []
    interactions: InteractionSummary = InteractionSummary()
    reports: list[ReportRef] = []

    # Narrative + evidence
    ai_summary: str = ""
    recommendations: list[str] = []
    rag_sources: list[str] = []
    evidence: list[EvidenceItem] = []

    # Provenance: how many records of each kind fed this twin.
    data_sources: dict[str, int] = {}
    disclaimer: str = (
        "This Digital Twin is an automated, aggregated view of prior analyses for "
        "educational support only. It is NOT a diagnosis, medical record or a "
        "substitute for professional judgement. All values must be verified by a "
        "qualified clinician."
    )


# --------------------------------------------------------------------------
# Patients list + analytics + recalculation
# --------------------------------------------------------------------------
class PatientListItem(BaseModel):
    """A patient row for the Digital Twin picker."""

    patient_id: str
    patient_name: str
    report_count: int = 0
    last_seen: datetime | None = None
    health_score: float | None = None
    risk_level: RiskLevel | None = None


class DigitalTwinAnalytics(BaseModel):
    """Population-level analytics across all patients' latest twins."""

    total_patients: int = 0
    average_health_score: float = 0.0
    patients_at_risk: int = 0                       # high or critical
    risk_distribution: dict[str, int] = {}
    status_distribution: dict[str, int] = {}
    top_diseases: list[dict[str, Any]] = []
    recomputed_at: datetime | None = None


class RecalculateRequest(BaseModel):
    """Body for ``POST /digital-twin/recalculate``."""

    patient_id: str | None = None                   # None → recalculate everyone


class RecalculateResult(BaseModel):
    """Outcome of a recalculation."""

    recalculated: int = 0
    patients: list[str] = []
    took_ms: float = 0.0
