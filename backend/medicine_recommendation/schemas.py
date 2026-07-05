"""Pydantic models for the Medicine Recommendation API (frontend contract).

These types are the *stable* boundary between the backend and the React UI. A
:class:`RecommendationReport` is assembled by the service from two sources — the
existing medicine dataset/index (structured drug data + substitutes) and the RAG
knowledge base (evidence-based fields + a grounded summary) — but the shape the
UI consumes is intentionally simple and framework-agnostic.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlternativeKind(str, Enum):
    """Why a medicine is offered as an alternative (drives grouping in the UI)."""

    GENERIC_EQUIVALENT = "generic_equivalent"   # same molecule, usually cheaper
    BRAND_ALTERNATIVE = "brand_alternative"     # a listed substitute brand
    SIMILAR = "similar"                         # same therapeutic/action class


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class MedicineRecommendRequest(BaseModel):
    """Input for ``POST /medicine/recommend``.

    ``medicines`` are names as detected by OCR or typed by the user. Everything
    else is optional and degrades gracefully.
    """

    medicines: list[str] = Field(default_factory=list)
    include_rag: bool = True                     # evidence-based enrichment
    max_alternatives: int = Field(default=5, ge=1, le=15)
    persist: bool = True                         # save this report to history
    source_record_id: str | None = None          # optional link to an OCR record


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
class DrugInfo(BaseModel):
    """Structured drug information card (Requirement 2)."""

    generic_name: str = ""
    brand_name: str = ""
    drug_class: str = ""                          # mechanism / action class
    therapeutic_category: str = ""               # therapeutic class
    available_strengths: list[str] = []
    prescription_required: str = "unknown"       # "yes" | "no" | "unknown"
    prescription_note: str = ""
    common_uses: list[str] = []
    common_side_effects: list[str] = []
    contraindications: list[str] = []
    pregnancy_safety: str = ""
    food_interactions: str = ""
    storage_instructions: str = ""
    habit_forming: str = ""                       # "Yes" | "No" | ""


class AlternativeMedicine(BaseModel):
    """One suggested alternative, with the reason it is suggested (Requirement 3)."""

    name: str
    kind: AlternativeKind
    reason: str = ""
    match_score: float = 0.0                      # 0..100 similarity/relevance
    therapeutic_category: str | None = None


class RelatedDocument(BaseModel):
    """A knowledge-base passage retrieved by RAG (Requirement 4)."""

    source: str
    excerpt: str = ""
    score: float = 0.0


class MedicineRecommendation(BaseModel):
    """The full recommendation for a single detected medicine."""

    detected_name: str                            # name as supplied / OCR'd
    resolved_name: str = ""                       # canonical dataset name
    matched: bool = False
    match_score: float = 0.0                      # 0..100 resolution confidence

    drug_info: DrugInfo = DrugInfo()
    generic_equivalents: list[AlternativeMedicine] = []
    brand_alternatives: list[AlternativeMedicine] = []
    similar_medicines: list[AlternativeMedicine] = []

    warnings: list[str] = []
    ai_summary: str = ""                          # per-medicine narrative
    rag_sources: list[str] = []
    related_documents: list[RelatedDocument] = []
    confidence_score: float = 0.0                 # 0..100 overall confidence
    notes: list[str] = []                         # provenance / caveats


# --------------------------------------------------------------------------
# Full report
# --------------------------------------------------------------------------
class RecommendationReport(BaseModel):
    """Complete medicine-recommendation report (the frontend contract)."""

    id: str | None = None
    created_at: datetime | None = None

    medicines: list[MedicineRecommendation] = []
    medicine_count: int = 0
    overall_confidence: float = 0.0               # 0..100
    ai_report: str = ""                           # AI recommendation report (Req 3)
    sources: list[str] = []                       # provenance (dataset / rag)
    warnings: list[str] = []
    provider: str = "medicine-recommendation-engine"
    disclaimer: str = (
        "This automated medicine information and the suggested alternatives are "
        "for educational support only and are NOT a prescription or medical "
        "advice. Alternatives (including generic equivalents) must only be "
        "substituted on the advice of a qualified doctor or pharmacist, who will "
        "account for your specific condition, allergies and other medicines."
    )


# --------------------------------------------------------------------------
# History (list + detail)
# --------------------------------------------------------------------------
class RecommendationHistoryItem(BaseModel):
    """Lightweight row for the recommendation-history list view."""

    id: str
    created_at: datetime
    medicines: list[str] = []
    medicine_count: int = 0
    overall_confidence: float = 0.0


class RecommendationHistoryPage(BaseModel):
    """A page of history items plus pagination metadata."""

    items: list[RecommendationHistoryItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
