"""Context reranking for the Evidence Engine (pure, no I/O).

The vector store already ranks chunks by embedding cosine similarity, but that
single signal can miss passages that are lexically on-point yet only
moderately close in embedding space (e.g. an exact drug name match buried in
a longer chunk). This reranker blends the original semantic similarity with a
lightweight lexical-overlap score between the query and each chunk, then
re-sorts and trims to ``top_k`` — a hybrid re-ranking pass that needs no extra
model or network call, keeping the whole pipeline offline-safe.
"""

from __future__ import annotations

import logging
import re

from backend.evidence_engine.schemas import RetrievedChunk

logger = logging.getLogger("evidence_engine.reranker")

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

# Semantic similarity dominates; lexical overlap only nudges the ordering.
_SEMANTIC_WEIGHT = 0.75
_LEXICAL_WEIGHT = 0.25

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "of", "for", "and", "or",
    "to", "in", "on", "with", "what", "how", "does", "do", "can", "i", "it",
    "this", "that", "be", "as", "at", "by", "from",
})


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1}


def _lexical_overlap(query_tokens: set[str], chunk_text: str) -> float:
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokens(chunk_text)
    if not chunk_tokens:
        return 0.0
    overlap = len(query_tokens & chunk_tokens)
    return overlap / len(query_tokens)


def rerank(query: str, chunks: list[RetrievedChunk], *, top_k: int | None = None) -> list[RetrievedChunk]:
    """Re-score and re-sort ``chunks`` by blended semantic + lexical relevance to ``query``."""
    if not chunks:
        return []
    query_tokens = _tokens(query)

    reranked: list[RetrievedChunk] = []
    for chunk in chunks:
        lexical = _lexical_overlap(query_tokens, chunk.text)
        blended = round(
            _SEMANTIC_WEIGHT * chunk.similarity_score + _LEXICAL_WEIGHT * lexical, 4
        )
        reranked.append(chunk.model_copy(update={"rerank_score": min(1.0, blended)}))

    reranked.sort(key=lambda c: c.rerank_score, reverse=True)
    result = reranked[:top_k] if top_k else reranked
    logger.debug("Reranked %d -> %d chunk(s) for query %r", len(chunks), len(result), query[:80])
    return result
