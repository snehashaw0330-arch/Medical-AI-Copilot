"""Semantic retrieval for the Evidence Engine.

Thin, async-friendly adapter over the existing RAG subsystem
(:mod:`backend.rag.retriever`) — this module does **not** stand up a second
embedder or vector store. It only re-shapes :class:`~backend.rag.vector_store.
RetrievedChunk` hits into the Evidence Engine's own :class:`RetrievedChunk`
schema (with a stable ``chunk_id`` and a readable ``source_title``) so the
rest of the pipeline (reranker, citation builder, response builder) never has
to know ChromaDB exists.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

from backend.evidence_engine.schemas import RetrievedChunk
from backend.rag.retriever import get_retriever

logger = logging.getLogger("evidence_engine.retriever")


def _source_title(source: str, index: int) -> str:
    """Turn a file path/name into a readable title (mirrors evidence_verification's convention)."""
    if source and source.strip().lower() not in ("", "unknown"):
        base = source.replace("\\", "/").split("/")[-1]
        stem = base.rsplit(".", 1)[0] if "." in base else base
        title = stem.replace("_", " ").replace("-", " ").title()
        return title or f"Document {index + 1}"
    return f"Document {index + 1}"


def _chunk_id(source: str, text: str, index: int) -> str:
    digest = hashlib.sha1(f"{source}:{text[:200]}".encode("utf-8")).hexdigest()[:12]
    return f"chunk-{index + 1}-{digest}"


def available() -> bool:
    """True only if the underlying embedder + vector store are both usable."""
    return get_retriever().available()


async def aretrieve(
    query: str,
    *,
    top_k: int | None = None,
    min_similarity: float | None = None,
) -> list[RetrievedChunk]:
    """Retrieve the most relevant medical-knowledge passages for ``query``."""
    if not query.strip():
        return []
    hits = await asyncio.to_thread(
        get_retriever().retrieve, query, top_k=top_k, min_similarity=min_similarity
    )
    chunks = [
        RetrievedChunk(
            chunk_id=_chunk_id(hit.source, hit.text, i),
            text=hit.text,
            source_title=_source_title(hit.source, i),
            source=hit.source,
            similarity_score=round(float(hit.score), 4),
            rerank_score=round(float(hit.score), 4),   # default until reranked
            metadata=hit.metadata or {},
        )
        for i, hit in enumerate(hits)
    ]
    logger.info("Retrieved %d chunk(s) for query %r", len(chunks), query[:80])
    return chunks
