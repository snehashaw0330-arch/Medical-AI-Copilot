"""Service layer for the Evidence-Based Medical Response Engine (async).

Orchestrates the full pipeline described in the module's workflow:

    question -> retrieve (ChromaDB) -> rerank -> cite -> generate -> respond

and owns the concerns the pure engine stages stay out of:

* **Chat sessions** — a small in-memory, TTL+LRU store of recent turns per
  ``session_id`` so ``/evidence/chat`` can answer follow-up questions with
  context, without ever mutating the RAG knowledge base itself.
* **Persistence** — best-effort async storage of every query/response for the
  Evidence Explorer history view.

Design contract: async everywhere, best-effort persistence, and structured
logging — a failure in retrieval, reranking or persistence never raises past
the router as anything other than a clean, informative response.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict

from sqlalchemy import Column, DateTime, Float, Integer, String, Boolean, delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON

from backend.config import settings
from backend.evidence_engine import citation_builder, reranker, response_builder
from backend.evidence_engine.retriever import aretrieve
from backend.evidence_engine.schemas import (
    EvidenceChatRequest,
    EvidenceHistoryItem,
    EvidenceQueryRequest,
    EvidenceResponse,
)

import logging

logger = logging.getLogger("evidence_engine.service")

Base = declarative_base()


# ==========================================================================
# Persistence
# ==========================================================================
class EvidenceRecord(Base):
    __tablename__ = "evidence_queries"

    id = Column(String(32), primary_key=True)
    session_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    query = Column(String(1024), default="")
    confidence_score = Column(Float, default=0.0)
    source_count = Column(Integer, default=0)
    evidence_found = Column(Boolean, default=False)
    report = Column(JSON, nullable=False)

    def item(self) -> EvidenceHistoryItem:
        return EvidenceHistoryItem(
            id=self.id, session_id=self.session_id, created_at=self.created_at,
            query=self.query or "", confidence_score=self.confidence_score or 0.0,
            source_count=self.source_count or 0, evidence_found=bool(self.evidence_found),
        )


_engine = create_async_engine(
    settings.EVIDENCE_ENGINE_DB_URL, echo=False, pool_pre_ping=True, future=True
)
_Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession
)
_db_init_lock = asyncio.Lock()
_db_ready = False


async def _ensure_db() -> None:
    global _db_ready
    if _db_ready:
        return
    async with _db_init_lock:
        if _db_ready:
            return
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_ready = True
        logger.info("Evidence Engine history store ready (%s)",
                    settings.EVIDENCE_ENGINE_DB_URL.split("://")[0])


# ==========================================================================
# In-memory chat session store (TTL + LRU, mirrors the copilot session pattern)
# ==========================================================================
class _ChatSessions:
    def __init__(self, ttl: int, max_sessions: int) -> None:
        self._ttl = ttl
        self._max = max(1, max_sessions)
        self._store: OrderedDict[str, tuple[float, list[tuple[str, str]]]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get_history(self, session_id: str) -> list[tuple[str, str]]:
        async with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return []
            ts, turns = entry
            if time.time() - ts > self._ttl:
                self._store.pop(session_id, None)
                return []
            self._store.move_to_end(session_id)
            return list(turns)

    async def append(self, session_id: str, question: str, answer: str) -> None:
        async with self._lock:
            _, turns = self._store.get(session_id, (0.0, []))
            turns = (turns + [(question, answer)])[-10:]
            self._store[session_id] = (time.time(), turns)
            self._store.move_to_end(session_id)
            while len(self._store) > self._max:
                self._store.popitem(last=False)


def _format_history(turns: list[tuple[str, str]]) -> str:
    if not turns:
        return ""
    lines = []
    for q, a in turns[-5:]:
        lines.append(f"User: {q}\nAssistant: {a}")
    return "\n\n".join(lines)


# ==========================================================================
# Service
# ==========================================================================
class EvidenceEngineService:
    def __init__(self) -> None:
        self._sessions = _ChatSessions(
            settings.EVIDENCE_ENGINE_SESSION_TTL, settings.EVIDENCE_ENGINE_MAX_SESSIONS
        )

    async def aquery(self, req: EvidenceQueryRequest, *, session_id: str | None = None,
                      history: str = "", retrieval_query: str | None = None) -> EvidenceResponse:
        t0 = time.perf_counter()

        # In chat follow-ups the caller can widen the search beyond the raw
        # message (e.g. "What about its interactions?") using recent topic
        # context, while the displayed query/prompt still uses req.query.
        search_query = retrieval_query or req.query

        top_k = req.top_k or settings.EVIDENCE_ENGINE_TOP_K
        rerank_top_k = req.rerank_top_k or settings.EVIDENCE_ENGINE_RERANK_TOP_K
        min_similarity = req.min_similarity if req.min_similarity is not None else settings.EVIDENCE_ENGINE_MIN_SIMILARITY

        chunks = await aretrieve(search_query, top_k=top_k, min_similarity=min_similarity)
        if req.use_reranking:
            chunks = reranker.rerank(search_query, chunks, top_k=rerank_top_k)
        else:
            chunks = chunks[:rerank_top_k]

        citations = citation_builder.build(search_query, chunks)
        answer, confidence, provider = await response_builder.build_response(
            req.query, chunks, citations, history=history,
        )

        result = EvidenceResponse(
            session_id=session_id,
            query=req.query,
            response=answer,
            citations=citations,
            retrieved_chunks=chunks,
            confidence_score=confidence,
            evidence_found=bool(chunks),
            provider=provider,
            duration_ms=round((time.perf_counter() - t0) * 1000.0, 1),
            sources=sorted({c.source_title for c in chunks}),
        )

        if req.persist:
            result.id = await self._save(result)
        return result

    async def achat(self, req: EvidenceChatRequest) -> EvidenceResponse:
        session_id = req.session_id or uuid.uuid4().hex
        history_turns = await self._sessions.get_history(session_id)
        history = _format_history(history_turns)

        # Widen retrieval for short follow-ups ("What about its interactions?")
        # by folding in the recent turns' questions, so the search stays on
        # topic even when the new message alone lacks that context.
        retrieval_query = req.message
        if history_turns:
            recent_topics = " ".join(q for q, _ in history_turns[-2:])
            retrieval_query = f"{recent_topics} {req.message}".strip()

        query_req = EvidenceQueryRequest(
            query=req.message, top_k=req.top_k, rerank_top_k=req.rerank_top_k,
            min_similarity=req.min_similarity, use_reranking=req.use_reranking,
            persist=req.persist,
        )
        result = await self.aquery(
            query_req, session_id=session_id, history=history, retrieval_query=retrieval_query,
        )
        await self._sessions.append(session_id, req.message, result.response)
        return result

    # -- persistence -------------------------------------------------------
    async def _save(self, result: EvidenceResponse) -> str | None:
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            result.id = record_id
            row = EvidenceRecord(
                id=record_id, session_id=result.session_id, created_at=result.created_at,
                query=result.query[:1024], confidence_score=result.confidence_score,
                source_count=len(result.sources), evidence_found=result.evidence_found,
                report=result.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info("Saved evidence query %s (confidence=%.0f, sources=%d)",
                        record_id, result.confidence_score, len(result.sources))
            return record_id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save evidence query")
            return None

    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(EvidenceRecord.id))) or 0
            stmt = (
                select(EvidenceRecord)
                .order_by(EvidenceRecord.created_at.desc())
                .offset((page - 1) * page_size).limit(page_size)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return {
            "items": [r.item() for r in rows], "total": int(total),
            "page": page, "page_size": page_size,
            "pages": (int(total) + page_size - 1) // page_size,
        }

    async def get_history(self, record_id: str) -> dict | None:
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(EvidenceRecord, record_id)
            return row.report if row else None

    async def clear_history(self) -> int:
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(EvidenceRecord.id))) or 0
            await session.execute(delete(EvidenceRecord))
            await session.commit()
        logger.info("Cleared evidence engine history (%d records)", count)
        return int(count)


_SERVICE: EvidenceEngineService | None = None


def get_service() -> EvidenceEngineService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = EvidenceEngineService()
    return _SERVICE
