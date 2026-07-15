"""Pydantic models for the Evidence-Based Medical Response Engine (frontend contract).

Every AI-generated medical response produced by this engine is grounded in
medical evidence retrieved from the RAG knowledge base **before** generation:
retrieve -> rerank -> generate -> cite. These types are the stable boundary
between that pipeline and the React "Evidence Explorer" page.

The module only *reads* from the RAG knowledge base and never mutates it or
any other subsystem.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================================================
# Request
# ==========================================================================
class EvidenceQueryRequest(BaseModel):
    """Input for ``POST /evidence/query`` — a single grounded question."""

    query: str
    top_k: int | None = Field(default=None, ge=1, le=20)
    rerank_top_k: int | None = Field(default=None, ge=1, le=20)
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    use_reranking: bool = True
    persist: bool = True


class EvidenceChatRequest(BaseModel):
    """Input for ``POST /evidence/chat`` — a turn in an ongoing evidence-grounded chat."""

    message: str
    session_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    rerank_top_k: int | None = Field(default=None, ge=1, le=20)
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    use_reranking: bool = True
    persist: bool = True


# ==========================================================================
# Building blocks
# ==========================================================================
class RetrievedChunk(BaseModel):
    """One passage retrieved from the vector database (before/after reranking)."""

    chunk_id: str
    text: str
    source_title: str
    source: str = ""
    similarity_score: float = 0.0     # 0..1 raw vector-search similarity
    rerank_score: float = 0.0         # 0..1 score after semantic reranking
    metadata: dict = Field(default_factory=dict)


class Citation(BaseModel):
    """A numbered reference linking part of the response to its source evidence."""

    citation_id: str                  # e.g. "1", "2" — matches [1], [2] inline markers
    chunk_id: str
    source_title: str
    source: str = ""
    snippet: str = ""                 # short excerpt with matched terms highlighted (**bold**)
    similarity_score: float = 0.0


# ==========================================================================
# Full result (response of POST /evidence/query and POST /evidence/chat)
# ==========================================================================
class EvidenceResponse(BaseModel):
    id: str | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    timestamp: datetime = Field(default_factory=utcnow)

    query: str = ""
    response: str = ""                              # the AI-generated, grounded response

    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)

    confidence_score: float = 0.0                    # 0..100
    evidence_found: bool = False
    provider: str = "offline"                         # LLM provider used ("openai"|"gemini"|"claude"|...|"offline")
    duration_ms: float = 0.0

    sources: list[str] = Field(default_factory=list)  # unique source titles
    disclaimer: str = (
        "This response is generated from retrieved medical knowledge-base evidence and is "
        "informational only. It is not a substitute for professional medical advice — always "
        "confirm with a licensed pharmacist or doctor before acting on it."
    )


# ==========================================================================
# History (list + detail)
# ==========================================================================
class EvidenceHistoryItem(BaseModel):
    id: str
    session_id: str | None = None
    created_at: datetime
    query: str = ""
    confidence_score: float = 0.0
    source_count: int = 0
    evidence_found: bool = False


class EvidenceHistoryPage(BaseModel):
    items: list[EvidenceHistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
