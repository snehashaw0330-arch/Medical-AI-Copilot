"""Pydantic models for the Drug Interaction Analysis API (frontend contract).

These types are the *stable* boundary between the backend and the React UI.
They are intentionally framework-agnostic: the same shapes are produced whether
the underlying knowledge comes from the bundled JSON, a CSV/SQLite store or a
future live API (OpenFDA / RxNorm / DrugBank).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Five-level clinical severity scale (ordering matters — see utils)."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class InteractionCheckRequest(BaseModel):
    """Input for ``POST /interactions/check``.

    ``medicines`` are free-text names (typically straight from OCR); the service
    resolves them to known drugs by alias + fuzzy matching before analysis.
    """

    medicines: list[str] = Field(default_factory=list, min_length=0)
    include_rag: bool = True          # enrich with knowledge-base context
    persist: bool = True              # save this analysis to interaction history
    source_record_id: str | None = None  # optional link to an OCR history record


# --------------------------------------------------------------------------
# Pairwise drug–drug interaction
# --------------------------------------------------------------------------
class DrugDrugInteraction(BaseModel):
    """A single pairwise interaction between two (or more) medicines."""

    medicines: list[str]              # the drugs involved (display names)
    severity: Severity = Severity.NONE
    clinical_risk: str = ""           # short risk label, e.g. "Major bleeding"
    explanation: str = ""             # why the interaction happens
    recommendation: str = ""          # what to do about it
    clinical_notes: str = ""          # extra guidance for clinicians
    sources: list[str] = []           # provenance: "dataset", "rag", "openfda"…


# --------------------------------------------------------------------------
# Per-medicine warning profile (food / alcohol / organ / population)
# --------------------------------------------------------------------------
class MedicineWarnings(BaseModel):
    """Non-pairwise warnings that apply to a single medicine on its own."""

    medicine: str
    matched: bool = False             # True if resolved to a known drug
    contraindications: list[str] = []
    food: list[str] = []
    alcohol: list[str] = []
    pregnancy: list[str] = []
    breastfeeding: list[str] = []
    kidney: list[str] = []
    liver: list[str] = []
    age_restrictions: list[str] = []


# --------------------------------------------------------------------------
# Full report
# --------------------------------------------------------------------------
class InteractionReport(BaseModel):
    """Complete analysis returned by ``/interactions/check`` and stored history."""

    id: str | None = None
    created_at: datetime | None = None
    medicines: list[str] = []         # the medicines that were analysed
    resolved_medicines: list[str] = []  # canonical names actually matched
    unmatched_medicines: list[str] = []  # names we could not resolve to a drug

    interactions: list[DrugDrugInteraction] = []
    warnings: list[MedicineWarnings] = []

    overall_risk: Severity = Severity.NONE
    risk_counts: dict[str, int] = {}  # severity -> count (for badges/summary)
    summary: str = ""                 # human-readable headline
    recommendations: list[str] = []   # de-duplicated, prioritised actions

    rag_notes: str | None = None      # extra context from the knowledge base
    rag_sources: list[str] = []

    provider: str = "local-dataset"   # which knowledge source produced this
    disclaimer: str = (
        "This automated drug-interaction analysis is for educational support "
        "only and is not a substitute for professional medical or pharmacist "
        "advice. Always confirm with a qualified clinician before making any "
        "decision about medication."
    )


# --------------------------------------------------------------------------
# History (list + detail)
# --------------------------------------------------------------------------
class InteractionHistoryItem(BaseModel):
    """Lightweight row for the interaction-history list view."""

    id: str
    created_at: datetime
    medicines: list[str] = []
    medicine_count: int = 0
    interaction_count: int = 0
    overall_risk: Severity = Severity.NONE
    summary: str = ""


class InteractionHistoryPage(BaseModel):
    """A page of history items plus pagination metadata."""

    items: list[InteractionHistoryItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
