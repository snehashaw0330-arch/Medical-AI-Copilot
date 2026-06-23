"""RAG service layer — the orchestration brain of the subsystem.

Combines retrieval (vector search) with generation (LLM or offline extractive
synthesis) and exposes a small, stable API the FastAPI router calls:

* :meth:`RAGService.status`          — health / index stats
* :meth:`RAGService.index`           — (re)build the index from documents/
* :meth:`RAGService.aquery`          — answer a free-text question
* :meth:`RAGService.amedicine_info`  — structured drug profile(s) + interactions

Generation is provider-agnostic (Requirement 19):

* **openai**  — GPT models via the ``openai`` SDK (needs ``OPENAI_API_KEY``)
* **gemini**  — Gemini via ``google-genai``        (needs ``GEMINI_API_KEY``)
* **offline** — no LLM: answers are synthesised directly from retrieved
                context. The system therefore works fully offline and only gets
                *better* when an LLM key is added — it never depends on one.

Every public entry point logs and degrades gracefully; a missing dependency or
unindexed store yields an informative response, never a 500 that breaks the app.
"""

from __future__ import annotations

import asyncio
import re
import time

from backend.rag.config import config, get_logger
from backend.rag import prompts
from backend.rag.document_loader import document_summary
from backend.rag.retriever import get_retriever
from backend.rag.vector_store import RetrievedChunk

logger = get_logger("rag.service")


# ==========================================================================
# LLM generation (pluggable, lazy, optional)
# ==========================================================================
def _generate_openai(system: str, user: str) -> str:
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=config.LLM_TEMPERATURE,
        max_tokens=config.LLM_MAX_TOKENS,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _generate_gemini(system: str, user: str) -> str:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=f"{system}\n\n{user}",
        config=types.GenerateContentConfig(
            temperature=config.LLM_TEMPERATURE,
            max_output_tokens=config.LLM_MAX_TOKENS,
        ),
    )
    return (resp.text or "").strip()


def generate(system: str, user: str) -> tuple[str | None, str]:
    """Run the configured LLM. Returns (answer_or_None, provider_used).

    Returns ``(None, "offline")`` when no LLM is configured or the call fails,
    signalling the caller to fall back to extractive synthesis.
    """
    provider = config.resolved_llm_provider()
    if provider == "offline":
        return None, "offline"
    try:
        if provider == "openai":
            return _generate_openai(system, user), "openai"
        if provider == "gemini":
            return _generate_gemini(system, user), "gemini"
        logger.warning("Unknown LLM provider '%s' — using offline mode.", provider)
    except Exception as exc:  # noqa: BLE001 — any LLM failure -> offline fallback
        logger.error("LLM generation failed (%s); falling back to offline: %s", provider, exc)
    return None, "offline"


# ==========================================================================
# Offline extractive synthesis (no LLM required)
# ==========================================================================
# Map knowledge-doc section headings to the structured medicine fields.
_FIELD_SYNONYMS: dict[str, list[str]] = {
    "uses": ["uses", "use", "indication", "indications", "what is", "about", "overview"],
    "dosage": ["dosage", "dose", "dosing", "administration", "how to take"],
    "side_effects": ["side effects", "side effect", "adverse effects", "adverse reactions"],
    "drug_interactions": ["drug interactions", "interactions", "drug interaction"],
    "contraindications": ["contraindications", "contraindication", "do not use", "when not to use"],
    "warnings": ["warnings", "warning", "precautions", "precaution"],
    "pregnancy_safety": ["pregnancy", "pregnancy safety", "lactation", "breastfeeding"],
    "food_interactions": ["food interactions", "food interaction", "food", "alcohol", "with food"],
    "storage": ["storage", "store", "storing"],
}

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s*(.+?)\s*#*\s*$")
_BOLD_HEADING_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?\s*$")
_COLON_HEADING_RE = re.compile(r"^\s*([A-Z][A-Za-z /&-]{2,40}):\s*(.*)$")


def _match_field(heading: str) -> str | None:
    h = heading.strip().lower()
    for field, names in _FIELD_SYNONYMS.items():
        if any(h == n or h.startswith(n) for n in names):
            return field
    return None


def extract_structured_fields(text: str) -> dict[str, str]:
    """Parse markdown/structured text into the 9 medicine fields (best effort).

    Recognises ``# Heading``, ``**Heading**`` and ``Heading:`` styles. Content
    under a recognised heading is assigned to the matching field. Works fully
    offline on the well-structured knowledge documents shipped with the project.
    """
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = None
        inline = None
        m = _HEADING_RE.match(line)
        if m:
            heading = m.group(2)
        else:
            m = _BOLD_HEADING_RE.match(line)
            if m:
                heading = m.group(1)
            else:
                m = _COLON_HEADING_RE.match(line)
                if m:
                    heading = m.group(1)
                    inline = m.group(2)
        if heading is not None:
            current = _match_field(heading)
            if current and inline:
                fields.setdefault(current, []).append(inline.strip())
            continue
        if current and line.strip():
            fields.setdefault(current, []).append(line.strip())

    return {k: " ".join(v).strip() for k, v in fields.items() if v}


def _retrieval_confidence(chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    top = [c.score for c in chunks[: min(3, len(chunks))]]
    return round(sum(top) / len(top), 3)


def _offline_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    """Compose a readable answer purely from retrieved context."""
    if not chunks:
        return (
            "I couldn't find anything about that in the knowledge base yet. "
            "Try adding a relevant document, or consult a licensed pharmacist."
        )
    parts = [f"Based on the knowledge base:\n"]
    for i, c in enumerate(chunks[:3], 1):
        snippet = c.text.strip()
        if len(snippet) > 600:
            snippet = snippet[:600].rsplit(" ", 1)[0] + "…"
        parts.append(f"[{i}] ({c.source}) {snippet}")
    return "\n\n".join(parts)


# ==========================================================================
# Service
# ==========================================================================
class RAGService:
    """High-level orchestration over retrieval + generation."""

    def __init__(self) -> None:
        self.retriever = get_retriever()

    # -- status ------------------------------------------------------------
    def status(self) -> dict:
        embedder_ok = self.retriever.embedder.available()
        store_ok = self.retriever.store.available()
        count = self.retriever.count() if store_ok else 0
        return {
            "available": embedder_ok and store_ok,
            "embedder_available": embedder_ok,
            "vector_store_available": store_ok,
            "indexed_chunks": count,
            "is_indexed": count > 0,
            "embedding_model": config.EMBEDDING_MODEL,
            "vector_backend": config.VECTOR_BACKEND,
            "llm_provider": config.resolved_llm_provider(),
            "documents": document_summary(),
            "indexed_sources": self.retriever.store.sources() if store_ok else [],
        }

    # -- indexing ----------------------------------------------------------
    def index(self, *, reset: bool = True) -> dict:
        """Rebuild the index from the documents folder. Synchronous (CPU-bound)."""
        if not self.retriever.embedder.available():
            raise RuntimeError(
                "Embedding model unavailable. Install RAG deps: "
                "pip install sentence-transformers chromadb pypdf"
            )
        start = time.perf_counter()
        n_chunks = self.retriever.reindex_from_disk(reset=reset)
        elapsed = round(time.perf_counter() - start, 2)
        docs = document_summary()
        logger.info("Index rebuilt: %d chunks from %d documents in %ss", n_chunks, len(docs), elapsed)
        return {
            "indexed_chunks": n_chunks,
            "documents": len(docs),
            "document_list": [d["name"] for d in docs],
            "elapsed_seconds": elapsed,
            "vector_backend": config.VECTOR_BACKEND,
            "embedding_model": config.EMBEDDING_MODEL,
        }

    async def aindex(self, *, reset: bool = True) -> dict:
        return await asyncio.to_thread(self.index, reset=reset)

    # -- query -------------------------------------------------------------
    async def aquery(self, question: str, *, top_k: int | None = None) -> dict:
        """Answer a free-text question with retrieved context (Steps 3-5)."""
        if not self.retriever.available():
            return {
                "answer": "The knowledge base is not available. Install the RAG "
                "dependencies and build the index from the Knowledge Base page.",
                "confidence": 0.0,
                "provider": "unavailable",
                "sources": [],
                "chunks": [],
            }
        chunks = await asyncio.to_thread(self.retriever.retrieve, question, top_k=top_k)

        user_prompt = prompts.build_qa_prompt(question, chunks)
        answer, provider = await asyncio.to_thread(
            generate, prompts.SYSTEM_PROMPT, user_prompt
        )
        if answer is None:
            answer = _offline_answer(question, chunks)

        return {
            "answer": answer,
            "confidence": _retrieval_confidence(chunks),
            "provider": provider,
            "sources": sorted({c.source for c in chunks}),
            "chunks": [self._chunk_dict(c) for c in chunks],
            "safety_note": prompts.SAFETY_FOOTER,
        }

    # -- medicine intelligence (Requirements 8 + 9) ------------------------
    async def amedicine_info(self, medicines: list[str]) -> dict:
        """Structured profile per medicine + cross-medicine interaction check."""
        names = [m.strip() for m in medicines if m and m.strip()]
        if not names:
            return {"medicines": [], "interactions": None, "provider": "offline"}

        per_medicine = await asyncio.gather(
            *(self._one_medicine(name) for name in names)
        )

        interactions = None
        if len(names) > 1:
            interactions = await self._interactions(names)

        return {
            "medicines": per_medicine,
            "interactions": interactions,
            "provider": config.resolved_llm_provider(),
            "safety_note": prompts.SAFETY_FOOTER,
        }

    async def _one_medicine(self, name: str) -> dict:
        # Retrieve knowledge-base context for this drug.
        query = f"{name} uses dosage side effects interactions warnings pregnancy storage"
        chunks: list[RetrievedChunk] = []
        if self.retriever.available():
            chunks = await asyncio.to_thread(self.retriever.retrieve, query, top_k=config.TOP_K)

        # Offline structured extraction from the retrieved context.
        merged_text = "\n".join(c.text for c in chunks)
        structured = extract_structured_fields(merged_text)

        # Enrich from the existing medicine CSV index (uses / side effects).
        structured = self._enrich_from_csv(name, structured)

        # Optional LLM narrative summary grounded in the same context.
        summary, provider = await asyncio.to_thread(
            generate, prompts.SYSTEM_PROMPT, prompts.build_medicine_prompt(name, chunks)
        )
        if summary is None:
            summary = _offline_answer(f"What is {name}?", chunks) if chunks else (
                f"No knowledge-base entry found for {name}. "
                "Add a document about it to enrich this profile."
            )

        return {
            "name": name,
            "fields": {f: structured.get(f, "") for f in prompts.MEDICINE_FIELDS},
            "summary": summary,
            "confidence": _retrieval_confidence(chunks),
            "sources": sorted({c.source for c in chunks}),
            "chunks": [self._chunk_dict(c) for c in chunks],
        }

    async def _interactions(self, names: list[str]) -> dict:
        query = "drug interactions between " + " and ".join(names)
        chunks: list[RetrievedChunk] = []
        if self.retriever.available():
            chunks = await asyncio.to_thread(self.retriever.retrieve, query, top_k=config.TOP_K)
        answer, provider = await asyncio.to_thread(
            generate, prompts.SYSTEM_PROMPT, prompts.build_interaction_prompt(names, chunks)
        )
        if answer is None:
            answer = _offline_answer(query, chunks) if chunks else (
                "No drug-interaction information was found in the knowledge base "
                f"for: {', '.join(names)}. Please consult a pharmacist."
            )
        return {
            "medicines": names,
            "answer": answer,
            "confidence": _retrieval_confidence(chunks),
            "sources": sorted({c.source for c in chunks}),
        }

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _enrich_from_csv(name: str, structured: dict[str, str]) -> dict[str, str]:
        """Fill empty uses/side-effects from the existing medicine dataset."""
        try:
            from backend.ocr.medicine_intelligence import get_index

            index = get_index()
            matches = index.search(name, limit=1)
            if matches and matches[0].score >= 70:
                details = index.details(matches[0].name)
                if not structured.get("uses") and details.get("uses"):
                    structured["uses"] = "; ".join(details["uses"])
                if not structured.get("side_effects") and details.get("side_effects"):
                    structured["side_effects"] = "; ".join(details["side_effects"][:8])
        except Exception as exc:  # noqa: BLE001 — CSV enrichment is best-effort
            logger.debug("CSV enrichment skipped for %s: %s", name, exc)
        return structured

    @staticmethod
    def _chunk_dict(c: RetrievedChunk) -> dict:
        return {
            "text": c.text,
            "source": c.source,
            "score": c.score,
            "metadata": c.metadata,
        }


_SERVICE: RAGService | None = None


def get_rag_service() -> RAGService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RAGService()
    return _SERVICE
