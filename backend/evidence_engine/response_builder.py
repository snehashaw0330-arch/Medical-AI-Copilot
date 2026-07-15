"""Grounded response generation for the Evidence Engine.

Builds the final AI response strictly from the reranked evidence chunks —
this is the step that turns retrieval into an answer while minimizing
hallucination:

* the prompt instructs the model to answer **only** from the numbered
  evidence blocks and to cite them inline as ``[1]``, ``[2]`` …;
* generation uses the project's provider-agnostic LLM layer
  (:func:`backend.llm.get_llm`), which is offline-safe by design;
* when no LLM is configured (or generation fails), a deterministic
  extractive fallback composes the answer directly from the evidence text —
  every word is then, by construction, traceable to a source;
* a **confidence score** is derived purely from how strong the supporting
  evidence is, independent of which provider generated the prose, so a
  low-similarity retrieval is flagged as low-confidence even if the LLM
  produced a fluent-sounding answer (hallucination reduction).
"""

from __future__ import annotations

import logging

from backend.evidence_engine.schemas import Citation, RetrievedChunk
from backend.llm import get_llm

logger = logging.getLogger("evidence_engine.response_builder")

SYSTEM_PROMPT = (
    "You are MediSense's Evidence-Based Medical Response Engine. Answer using "
    "ONLY the numbered evidence blocks provided below — never invent facts, "
    "dosages, or drug interactions that are not present in the evidence. Cite "
    "the evidence you rely on inline as [1], [2], etc., matching the block "
    "numbers. If the evidence does not fully answer the question, say so "
    "plainly and note what is missing instead of guessing. Be concise, "
    "structured, and remind the reader this is informational, not a "
    "prescription."
)


def _format_evidence(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no relevant evidence retrieved)"
    blocks = []
    for i, c in enumerate(chunks, 1):
        score = c.rerank_score or c.similarity_score
        blocks.append(f"[{i}] (source: {c.source_title}, relevance: {score:.2f})\n{c.text}")
    return "\n\n".join(blocks)


def build_prompt(query: str, chunks: list[RetrievedChunk], history: str = "") -> str:
    context = _format_evidence(chunks)
    history_block = f"Conversation so far:\n{history}\n\n" if history else ""
    return (
        f"{history_block}Evidence retrieved from the medical knowledge base:\n\n{context}\n\n"
        f"Question: {query}\n\n"
        "Answer the question grounded strictly in the evidence above, citing sources "
        "inline as [1], [2] where relevant."
    )


def _offline_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    """Extractive fallback: compose an answer directly from the evidence text (no LLM required)."""
    if not chunks:
        return (
            "I couldn't find supporting evidence for that in the medical knowledge base. "
            "Try rephrasing the question, add a relevant document to the knowledge base, "
            "or consult a licensed pharmacist or doctor."
        )
    parts = ["Based on the retrieved medical evidence:\n"]
    for i, c in enumerate(chunks, 1):
        snippet = c.text.strip()
        if len(snippet) > 500:
            snippet = snippet[:500].rsplit(" ", 1)[0] + "…"
        parts.append(f"[{i}] ({c.source_title}) {snippet}")
    return "\n\n".join(parts)


def _grounding_confidence(chunks: list[RetrievedChunk]) -> float:
    """0..100 confidence derived purely from evidence strength (not the LLM's fluency)."""
    if not chunks:
        return 0.0
    top = [c.rerank_score or c.similarity_score for c in chunks[: min(3, len(chunks))]]
    return round((sum(top) / len(top)) * 100.0, 1)


async def build_response(
    query: str,
    chunks: list[RetrievedChunk],
    citations: list[Citation],
    *,
    history: str = "",
) -> tuple[str, float, str]:
    """Generate the grounded answer. Returns ``(response_text, confidence_score, provider)``."""
    confidence = _grounding_confidence(chunks)

    llm = get_llm()
    provider = "offline"
    answer: str | None = None
    if llm.available() and chunks:
        try:
            result = await llm.acomplete(
                system=SYSTEM_PROMPT,
                prompt=build_prompt(query, chunks, history=history),
                temperature=0.2,
                max_tokens=800,
            )
            answer = (result.text or "").strip() or None
            provider = result.provider or llm.name
        except Exception as exc:  # noqa: BLE001 — any LLM failure -> offline fallback
            logger.warning("LLM generation failed (%s); falling back to offline: %s", llm.name, exc)

    if not answer:
        answer = _offline_answer(query, chunks)
        provider = "offline"

    return answer, confidence, provider
