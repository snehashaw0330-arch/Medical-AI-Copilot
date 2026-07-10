"""Service layer for the Evidence Verification Engine (async).

Owns the concerns the pure engine stays out of:

* **RAG integration** — when the caller doesn't supply evidence, it retrieves it
  from the knowledge base; when the caller doesn't supply a response and asks the
  engine to generate one, it uses the RAG answer (so the whole pipeline —
  *retrieve → generate → verify* — runs server-side).
* **Caching** — an in-memory TTL + LRU cache keyed by a hash of the inputs, so
  repeated verification requests skip the retrieval + embedding work.
* **Persistence** — best-effort async storage of every verification for history.

Also exposes :func:`verify_response`, a coroutine any existing module (AI Chat,
Clinical Decision, …) can call to verify its own generated text before showing it.

Design contract: async everywhere, best-effort integration + persistence, and
structured logging — a failure in any of these never propagates out of a check.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict

from sqlalchemy import Column, DateTime, Float, Integer, String, delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON

from backend.config import settings
from backend.evidence_verification.schemas import (
    EvidenceInput,
    VerificationHistoryItem,
    VerificationRequest,
    VerificationResult,
)
from backend.evidence_verification.verification_engine import get_engine

logger = logging.getLogger("evidence_verification.service")

Base = declarative_base()


# ==========================================================================
# Persistence
# ==========================================================================
class VerificationRecord(Base):
    __tablename__ = "verification_reports"

    id = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source_module = Column(String(32), default="chat", index=True)
    question = Column(String(1024), default="")
    confidence = Column(Float, default=0.0)
    evidence_coverage = Column(Float, default=0.0)
    hallucination_risk = Column(String(16), default="medium", index=True)
    unsupported_claims = Column(Integer, default=0)
    report = Column(JSON, nullable=False)

    def item(self) -> VerificationHistoryItem:
        return VerificationHistoryItem(
            id=self.id, created_at=self.created_at, question=self.question or "",
            source_module=self.source_module or "chat", confidence=self.confidence or 0.0,
            evidence_coverage=self.evidence_coverage or 0.0,
            hallucination_risk=self.hallucination_risk or "medium",
            unsupported_claims=self.unsupported_claims or 0,
        )


_engine = create_async_engine(
    settings.VERIFICATION_DB_URL, echo=False, pool_pre_ping=True, future=True
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
        logger.info("Verification history store ready (%s)",
                    settings.VERIFICATION_DB_URL.split("://")[0])


# ==========================================================================
# Cache
# ==========================================================================
class _Cache:
    def __init__(self, ttl: int, size: int) -> None:
        self._ttl = ttl
        self._size = max(1, size)
        self._store: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    async def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, payload = entry
            if time.time() - ts > self._ttl:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return payload

    async def put(self, key: str, payload: dict) -> None:
        if not self.enabled:
            return
        async with self._lock:
            self._store[key] = (time.time(), payload)
            self._store.move_to_end(key)
            while len(self._store) > self._size:
                self._store.popitem(last=False)


def _cache_key(req: VerificationRequest, response: str, evidence: list[EvidenceInput]) -> str:
    payload = {
        "q": req.question.strip().lower(),
        "r": (response or "").strip(),
        "ev": sorted((e.source, e.text[:120]) for e in evidence),
        "m": req.source_module,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ==========================================================================
# Service
# ==========================================================================
class VerificationService:
    def __init__(self) -> None:
        self._cache = _Cache(settings.VERIFICATION_CACHE_TTL, settings.VERIFICATION_CACHE_SIZE)

    async def check(self, req: VerificationRequest) -> VerificationResult:
        t0 = time.perf_counter()

        response = req.response or ""
        evidence = list(req.evidence)
        retrieval_confidence = self._avg_score(evidence)
        generated = False

        # Retrieve evidence and/or generate the response via RAG when needed.
        need_generation = not response and req.generate_if_missing
        if not evidence or need_generation:
            rag = await self._rag(req.question, req.top_k)
            if not evidence:
                evidence = rag["evidence"]
                retrieval_confidence = rag["confidence"]
            if need_generation:
                response = rag["answer"]
                generated = True

        # Cache lookup (after we know the final response + evidence).
        key = _cache_key(req, response, evidence)
        if req.use_cache:
            cached = await self._cache.get(key)
            if cached is not None:
                logger.info("Verification cache hit (%s…)", key[:10])
                result = VerificationResult(**cached)
                result.cached = True
                if req.persist:
                    result.id = await self._save(result)
                return result

        result = await get_engine().verify(
            question=req.question, response=response, evidence=evidence,
            retrieval_confidence=retrieval_confidence, source_module=req.source_module,
            generated=generated,
        )
        result.duration_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        await self._cache.put(key, result.model_dump(mode="json"))
        if req.persist:
            result.id = await self._save(result)
        return result

    # -- RAG retrieval + generation (best-effort) --------------------------
    async def _rag(self, question: str, top_k: int | None) -> dict:
        try:
            from backend.rag.rag_service import get_rag_service

            info = await get_rag_service().aquery(question, top_k=top_k or settings.VERIFICATION_TOP_K)
            chunks = info.get("chunks", []) if isinstance(info, dict) else []
            evidence = [
                EvidenceInput(
                    text=c.get("text", ""), source=c.get("source", ""),
                    score=float(c.get("score", 0.0) or 0.0),
                )
                for c in chunks if c.get("text")
            ]
            return {
                "evidence": evidence,
                "answer": info.get("answer", "") if isinstance(info, dict) else "",
                "confidence": float(info.get("confidence", 0.0) or 0.0) if isinstance(info, dict) else 0.0,
            }
        except Exception as exc:  # noqa: BLE001 — verification still runs, just ungrounded
            logger.warning("RAG retrieval unavailable for verification: %s", exc)
            return {"evidence": [], "answer": "", "confidence": 0.0}

    @staticmethod
    def _avg_score(evidence: list[EvidenceInput]) -> float:
        scores = [e.score for e in evidence if e.score]
        return round(sum(scores) / len(scores), 4) if scores else 0.5

    # -- persistence -------------------------------------------------------
    async def _save(self, result: VerificationResult) -> str | None:
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            result.id = record_id
            row = VerificationRecord(
                id=record_id, created_at=result.created_at,
                source_module=result.source_module,
                question=result.question[:1024],
                confidence=result.metrics.confidence,
                evidence_coverage=result.metrics.evidence_coverage,
                hallucination_risk=result.metrics.hallucination_risk.value,
                unsupported_claims=result.metrics.unsupported_claims,
                report=result.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info("Saved verification %s (risk=%s, conf=%.0f)",
                        record_id, result.metrics.hallucination_risk.value, result.metrics.confidence)
            return record_id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save verification report")
            return None

    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(VerificationRecord.id))) or 0
            stmt = (
                select(VerificationRecord)
                .order_by(VerificationRecord.created_at.desc())
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
            row = await session.get(VerificationRecord, record_id)
            return row.report if row else None

    async def clear_history(self) -> int:
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(VerificationRecord.id))) or 0
            await session.execute(delete(VerificationRecord))
            await session.commit()
        logger.info("Cleared verification history (%d records)", count)
        return int(count)


_SERVICE: VerificationService | None = None


def get_service() -> VerificationService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = VerificationService()
    return _SERVICE


async def verify_response(
    question: str, response: str, *, source_module: str = "chat",
    evidence: list[EvidenceInput] | None = None, persist: bool = True,
) -> VerificationResult:
    """Verify an already-generated response. For reuse by other modules."""
    req = VerificationRequest(
        question=question, response=response, source_module=source_module,
        evidence=evidence or [], generate_if_missing=False, persist=persist,
    )
    return await get_service().check(req)
