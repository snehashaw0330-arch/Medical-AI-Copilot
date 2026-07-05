"""Medical Knowledge Agent — the SOLE gateway to the RAG knowledge base.

Per the architecture, no other agent queries RAG directly. This agent builds a
retrieval query from the resolved medicines and predicted disease, **sanitises it
against prompt injection** (security requirement), caches repeated queries
(performance requirement), and delegates to the existing RAG service. It returns
the answer, retrieved chunks, sources and retrieval confidence.
"""

from __future__ import annotations

from collections import OrderedDict

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys
from backend.agents.security import sanitize_rag_query

# Simple bounded in-process cache of RAG answers, keyed by the sanitised query.
_RAG_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_MAX = 128


def _cache_get(key: str) -> dict | None:
    if key in _RAG_CACHE:
        _RAG_CACHE.move_to_end(key)
        return _RAG_CACHE[key]
    return None


def _cache_put(key: str, value: dict) -> None:
    _RAG_CACHE[key] = value
    _RAG_CACHE.move_to_end(key)
    while len(_RAG_CACHE) > _CACHE_MAX:
        _RAG_CACHE.popitem(last=False)


class KnowledgeAgent(BaseAgent):
    name = ac.KNOWLEDGE
    title = "Medical Knowledge Agent"
    description = "The sole gateway to the RAG knowledge base — retrieve guidelines and clinical references."
    reads = (MemoryKeys.MEDICINES, MemoryKeys.DISEASE)
    writes = (MemoryKeys.KNOWLEDGE,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        medicines = await ctx.get(MemoryKeys.MEDICINES, {})
        disease = await ctx.get(MemoryKeys.DISEASE, {})

        names = (medicines or {}).get("names", [])
        predictions = (disease or {}).get("predictions", [])
        topic = predictions[0]["disease"] if predictions else ""
        if not topic and not names:
            return AgentOutcome.skipped("Nothing to look up in the knowledge base.")

        raw_query = (
            f"Clinical guidelines, precautions and references for "
            f"{topic or 'the prescribed medicines'}"
            + (f" with medications {', '.join(names[:6])}" if names else "")
        )
        query = sanitize_rag_query(raw_query)

        cached = _cache_get(query)
        if cached is not None:
            await ctx.set(MemoryKeys.KNOWLEDGE, {**cached, "cached": True})
            return AgentOutcome(summary="Knowledge retrieved (cache hit).",
                                confidence=cached.get("confidence"),
                                details={"sources": cached.get("sources", []), "cached": True})

        from backend.rag.rag_service import get_rag_service

        info = await get_rag_service().aquery(query)
        if not isinstance(info, dict) or info.get("provider") == "unavailable":
            await ctx.set(MemoryKeys.KNOWLEDGE, {"answer": None, "sources": [], "chunks": [],
                                                 "confidence": 0.0, "query": query})
            return AgentOutcome.skipped("Knowledge base unavailable.")

        result = {
            "answer": info.get("answer"),
            "sources": info.get("sources", []) or [],
            "chunks": [
                {"source": c.get("source"), "text": (c.get("text", "") or "")[:400],
                 "score": c.get("score")}
                for c in (info.get("chunks", []) or [])[:4]
            ],
            "confidence": float(info.get("confidence", 0.0) or 0.0),
            "query": query,
            "cached": False,
        }
        _cache_put(query, result)
        await ctx.set(MemoryKeys.KNOWLEDGE, result)
        return AgentOutcome(
            summary=f"Retrieved {len(result['sources'])} source(s) from the knowledge base.",
            confidence=result["confidence"],
            details={"sources": result["sources"]},
        )
