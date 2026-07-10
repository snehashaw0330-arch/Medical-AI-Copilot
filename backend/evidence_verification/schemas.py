"""Pydantic models for the Evidence Verification Engine (frontend contract).

The engine takes an AI-generated response (and the medical evidence retrieved for
the question) and estimates whether the response is well-supported or potentially
hallucinated. It breaks the response into atomic **claims**, scores each claim
against the retrieved evidence, and rolls the results up into auditable metrics:
evidence coverage, citation strength, hallucination risk and a confidence score.

These types are the stable boundary to the React "Evidence Verification" panel.
The module is purely additive — it only *reads* from the RAG knowledge base and
never mutates it or any other subsystem.
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
class ClaimSupport(str, Enum):
    """How well the retrieved evidence supports one claim."""

    SUPPORTED = "supported"          # strong evidence match
    WEAK = "weak"                    # partial / indirect support
    UNSUPPORTED = "unsupported"      # no evidence found (possible hallucination)
    CONTRADICTED = "contradicted"    # evidence appears to contradict the claim


class HallucinationRisk(str, Enum):
    """Five-level hallucination-risk scale."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SimilarityMethod(str, Enum):
    SEMANTIC = "semantic"            # embedding cosine (MiniLM)
    LEXICAL = "lexical"             # token-overlap fallback


# ==========================================================================
# Request
# ==========================================================================
class EvidenceInput(BaseModel):
    """An evidence document supplied by the caller (optional)."""

    text: str
    source: str = ""
    score: float = 0.0               # caller's own retrieval score (0..1)


class VerificationRequest(BaseModel):
    """Input for ``POST /verification/check``.

    * If ``response`` is omitted and ``generate_if_missing`` is true, the engine
      asks the RAG knowledge base to answer ``question`` and verifies that answer.
    * If ``evidence`` is omitted, the engine retrieves evidence for ``question``
      from the RAG knowledge base.

    This lets any existing module (AI Chat, Clinical Decision, …) submit its own
    generated text for verification, or delegate generation to the engine.
    """

    question: str
    response: str | None = None
    evidence: list[EvidenceInput] = Field(default_factory=list)
    source_module: str = "chat"      # provenance: which feature produced the text
    top_k: int | None = Field(default=None, ge=1, le=20)
    generate_if_missing: bool = True
    use_cache: bool = True
    persist: bool = True


# ==========================================================================
# Building blocks
# ==========================================================================
class Claim(BaseModel):
    """One atomic factual claim extracted from the response."""

    id: str
    text: str
    order: int                       # position in the response (for rendering)
    support: ClaimSupport = ClaimSupport.UNSUPPORTED
    similarity: float = 0.0          # 0..1 best evidence similarity
    best_evidence_id: str | None = None
    best_source: str | None = None
    matched_snippet: str = ""
    note: str = ""

    @property
    def is_unsupported(self) -> bool:
        return self.support in (ClaimSupport.UNSUPPORTED, ClaimSupport.CONTRADICTED)


class EvidenceDocument(BaseModel):
    """A retrieved evidence document + how it was used in verification."""

    id: str
    title: str
    source: str = ""
    snippet: str = ""
    retrieval_score: float = 0.0     # 0..1 retrieval relevance to the question
    relevance: float = 0.0           # 0..1 relevance to the response's claims
    supports_claims: list[str] = Field(default_factory=list)  # claim ids


class Citation(BaseModel):
    """Links one supported claim to its strongest evidence."""

    claim_id: str
    claim_text: str
    source: str
    evidence_id: str
    snippet: str = ""
    strength: float = 0.0            # 0..100 citation strength


class Contradiction(BaseModel):
    """A claim that appears to conflict with the retrieved evidence."""

    claim_id: str
    claim_text: str
    evidence_id: str
    source: str
    evidence_snippet: str = ""
    explanation: str = ""


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
    rationale: str = ""


class VerificationMetrics(BaseModel):
    """The headline numbers the panel renders."""

    evidence_coverage: float = 0.0           # 0..100 (% of claims supported)
    citation_strength: float = 0.0           # 0..100 (avg strength of citations)
    confidence: float = 0.0                  # 0..100
    hallucination_risk_score: float = 0.0    # 0..100 (higher = riskier)
    hallucination_risk: HallucinationRisk = HallucinationRisk.MEDIUM

    total_claims: int = 0
    supported_claims: int = 0
    weak_claims: int = 0
    unsupported_claims: int = 0
    contradicted_claims: int = 0
    missing_reference_count: int = 0


# ==========================================================================
# Full result (response of POST /verification/check)
# ==========================================================================
class VerificationResult(BaseModel):
    id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    cached: bool = False
    duration_ms: float = 0.0

    question: str = ""
    response: str = ""                       # the response that was verified
    source_module: str = "chat"
    method: SimilarityMethod = SimilarityMethod.LEXICAL
    generated: bool = False                  # was the response generated by RAG?

    metrics: VerificationMetrics = Field(default_factory=VerificationMetrics)
    confidence_breakdown: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)

    claims: list[Claim] = Field(default_factory=list)
    evidence: list[EvidenceDocument] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)   # claim texts
    missing_references: list[str] = Field(default_factory=list)   # claim texts

    verdict: str = ""                        # one-line human summary
    warnings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    provider: str = "evidence-verification-engine"
    disclaimer: str = (
        "Evidence verification is an automated safeguard that estimates how well an "
        "AI response is grounded in the retrieved medical knowledge base. It is not "
        "a guarantee of correctness; unsupported or contradicted claims must be "
        "checked by a qualified clinician before being relied upon."
    )


# ==========================================================================
# History (list + detail)
# ==========================================================================
class VerificationHistoryItem(BaseModel):
    id: str
    created_at: datetime
    question: str = ""
    source_module: str = "chat"
    confidence: float = 0.0
    evidence_coverage: float = 0.0
    hallucination_risk: HallucinationRisk = HallucinationRisk.MEDIUM
    unsupported_claims: int = 0


class VerificationHistoryPage(BaseModel):
    items: list[VerificationHistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
