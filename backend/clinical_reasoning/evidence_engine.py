"""Evidence retrieval for the reasoning pipeline (async, best-effort).

Wraps the existing RAG knowledge base and normalises whatever it returns into a
list of :class:`EvidenceCard` objects — the stable, UI-friendly shape the report
uses. The design contract matches the rest of the project:

* **Async & non-blocking** — the RAG service is awaited; nothing blocks the loop.
* **Best-effort** — any RAG failure (index missing, provider offline) degrades to
  "no evidence" and is reported as a warning; it never raises out of this module.
* **Additive** — it only *reads* from the RAG service; it never mutates it.
"""

from __future__ import annotations

import logging

from backend.clinical_reasoning.schemas import EvidenceCard
from backend.config import settings

logger = logging.getLogger("clinical_reasoning.evidence")


def _build_question(
    disease: str | None,
    diagnosis: str | None,
    symptoms: list[str],
    medicines: list[str],
) -> str:
    """Compose a focused knowledge-base query from the case context."""
    topic = disease or diagnosis or (symptoms[0] if symptoms else None)
    meds = ", ".join(medicines[:6])
    parts = ["Clinical evidence, management, monitoring and precautions for"]
    parts.append(topic or "the presenting problem")
    if meds:
        parts.append(f"with medications {meds}")
    if symptoms:
        parts.append(f"presenting with {', '.join(symptoms[:6])}")
    return " ".join(parts).strip()


def _cards_from_sources(info: dict) -> list[EvidenceCard]:
    """Turn a RAG response's ``sources`` / ``chunks`` into evidence cards."""
    cards: list[EvidenceCard] = []

    # Preferred: structured chunks (title/source/snippet/score) if the service
    # exposes them; fall back to the flat ``sources`` string list otherwise.
    chunks = info.get("chunks") or info.get("retrieved") or []
    if isinstance(chunks, list) and chunks and isinstance(chunks[0], dict):
        for i, ch in enumerate(chunks):
            cards.append(EvidenceCard(
                id=f"ev-{i + 1}",
                title=str(ch.get("title") or ch.get("source") or f"Evidence {i + 1}"),
                source=str(ch.get("source") or ch.get("document") or ""),
                snippet=str(ch.get("text") or ch.get("snippet") or "")[:600],
                relevance=float(ch.get("score") or ch.get("relevance") or 0.0),
                used_for="clinical grounding",
            ))
        return cards

    for i, src in enumerate(info.get("sources", []) or []):
        if isinstance(src, dict):
            title = str(src.get("title") or src.get("source") or f"Evidence {i + 1}")
            source = str(src.get("source") or src.get("document") or "")
            snippet = str(src.get("text") or src.get("snippet") or "")[:600]
            relevance = float(src.get("score") or src.get("relevance") or 0.0)
        else:
            title = str(src)
            source = str(src)
            snippet = ""
            relevance = 0.0
        cards.append(EvidenceCard(
            id=f"ev-{i + 1}", title=title, source=source,
            snippet=snippet, relevance=relevance, used_for="clinical grounding",
        ))
    return cards


class EvidenceEngine:
    """Retrieves and normalises clinical evidence from the RAG knowledge base."""

    async def gather(
        self,
        *,
        disease: str | None,
        diagnosis: str | None,
        symptoms: list[str],
        medicines: list[str],
        warnings: list[str],
    ) -> tuple[list[EvidenceCard], str | None, float]:
        """Return ``(cards, narrative, retrieval_confidence)``.

        ``retrieval_confidence`` is 0..1 and feeds the confidence engine; a low
        or zero value means the evidence step should not inflate certainty.
        """
        if not (settings.CLINICAL_REASONING_USE_RAG):
            return [], None, 0.0

        try:
            from backend.rag.rag_service import get_rag_service

            question = _build_question(disease, diagnosis, symptoms, medicines)
            info = await get_rag_service().aquery(question)
            if not isinstance(info, dict):
                return [], None, 0.0
            if info.get("provider") == "unavailable":
                warnings.append("Knowledge-base evidence was unavailable for this case.")
                return [], None, 0.0

            cards = _cards_from_sources(info)
            narrative = info.get("answer")
            confidence = float(info.get("confidence", 0.0) or 0.0)
            logger.info("Evidence engine retrieved %d card(s) (conf=%.2f)", len(cards), confidence)
            return cards, narrative, confidence
        except Exception as exc:  # noqa: BLE001 — evidence is optional enrichment
            logger.warning("Evidence retrieval skipped: %s", exc)
            warnings.append("Knowledge-base evidence retrieval failed for this case.")
            return [], None, 0.0


_ENGINE: EvidenceEngine | None = None


def get_engine() -> EvidenceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = EvidenceEngine()
    return _ENGINE
