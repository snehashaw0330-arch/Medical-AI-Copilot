"""Citation building for the Evidence Engine (pure, no I/O).

Turns the reranked evidence chunks into numbered :class:`Citation`s the
generated response can point back to (inline as ``[1]``, ``[2]`` …), each with
a short snippet where the query's own terms are **highlighted** — so the
Evidence Explorer UI can show the reader exactly which words in the source
matched their question (reference highlighting).
"""

from __future__ import annotations

import re

from backend.evidence_engine.schemas import Citation, RetrievedChunk

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
_SNIPPET_CHARS = 320


def _query_terms(query: str) -> list[str]:
    stop = {"the", "a", "an", "is", "are", "was", "were", "of", "for", "and", "or",
            "to", "in", "on", "with", "what", "how", "does", "do", "can", "i", "it"}
    terms = {t for t in _TOKEN_RE.findall(query.lower()) if t not in stop and len(t) > 2}
    return sorted(terms, key=len, reverse=True)  # longer terms first avoids partial-overlap highlighting


def _highlight(text: str, terms: list[str]) -> str:
    """Wrap query-term matches in ``**bold**`` markers (markdown, rendered by the frontend)."""
    if not terms:
        return text
    pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE)
    return pattern.sub(r"**\1**", text)


def _snippet(text: str, terms: list[str]) -> str:
    """Best-effort excerpt centered on the first query-term match, else the start of the chunk."""
    lower = text.lower()
    start = 0
    for term in terms:
        idx = lower.find(term)
        if idx != -1:
            start = max(0, idx - 80)
            break
    excerpt = text[start:start + _SNIPPET_CHARS].strip()
    if start > 0:
        excerpt = "…" + excerpt
    if start + _SNIPPET_CHARS < len(text):
        excerpt = excerpt + "…"
    return _highlight(excerpt, terms)


def build(query: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """Build one numbered citation per evidence chunk, strongest first."""
    terms = _query_terms(query)
    citations: list[Citation] = []
    for i, chunk in enumerate(chunks, start=1):
        citations.append(
            Citation(
                citation_id=str(i),
                chunk_id=chunk.chunk_id,
                source_title=chunk.source_title,
                source=chunk.source,
                snippet=_snippet(chunk.text, terms),
                similarity_score=chunk.rerank_score or chunk.similarity_score,
            )
        )
    return citations
