"""Service layer for the Clinical Reasoning Platform (async).

Thin orchestration around :class:`ReasoningEngine` that adds the cross-cutting
concerns the engine deliberately stays out of:

* **Caching** — an in-memory, TTL + LRU cache keyed by a stable hash of the
  request. The pipeline fans out to slow subsystems (disease model, RAG), so
  identical re-runs (e.g. a page refresh) are served instantly. Configurable via
  ``CLINICAL_REASONING_CACHE_TTL`` / ``CLINICAL_REASONING_CACHE_SIZE``.
* **Persistence** — best-effort async storage of every report for the history +
  timeline views, using the same SQLAlchemy-async contract as the other modules.
  A DB failure never breaks a reasoning run.
* **History / stats** — paginated reads and dashboard aggregates.

Design contract: async everywhere, best-effort integration, best-effort
persistence — a failure in any of these never propagates out of a reasoning run.
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

from backend.clinical_reasoning.reasoning_engine import get_engine as get_reasoning_engine
from backend.clinical_reasoning.schemas import (
    ClinicalReasoningReport,
    ReasoningHistoryItem,
    ReasoningRequest,
    utcnow,
)
from backend.config import settings

logger = logging.getLogger("clinical_reasoning.service")

Base = declarative_base()


# ==========================================================================
# Persistence model (kept inline — the module's only table)
# ==========================================================================
class ReasoningRecord(Base):
    """One persisted reasoning report (best-effort history)."""

    __tablename__ = "reasoning_reports"

    id = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source_record_id = Column(String(64), nullable=True)
    leading_disease = Column(String(255), nullable=True)
    medicine_count = Column(Integer, default=0)
    symptom_count = Column(Integer, default=0)
    step_count = Column(Integer, default=0)
    risk_level = Column(String(16), default="low", index=True)
    confidence = Column(Float, default=0.0)
    report = Column(JSON, nullable=False)

    def item(self) -> ReasoningHistoryItem:
        return ReasoningHistoryItem(
            id=self.id, created_at=self.created_at,
            leading_disease=self.leading_disease,
            medicine_count=self.medicine_count or 0,
            symptom_count=self.symptom_count or 0,
            risk_level=self.risk_level or "low",
            confidence=self.confidence or 0.0,
            step_count=self.step_count or 0,
        )


_engine = create_async_engine(
    settings.CLINICAL_REASONING_DB_URL, echo=False, pool_pre_ping=True, future=True
)
_Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession
)
_db_init_lock = asyncio.Lock()
_db_ready = False


async def _ensure_db() -> None:
    """Create the history table on first use (idempotent, race-safe)."""
    global _db_ready
    if _db_ready:
        return
    async with _db_init_lock:
        if _db_ready:
            return
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_ready = True
        logger.info(
            "Clinical-reasoning history store ready (%s)",
            settings.CLINICAL_REASONING_DB_URL.split("://")[0],
        )


# ==========================================================================
# In-memory TTL + LRU cache
# ==========================================================================
class _ReasoningCache:
    """Small, thread-safe-enough TTL+LRU cache for reasoning reports."""

    def __init__(self, ttl: int, size: int) -> None:
        self._ttl = ttl
        self._size = max(1, size)
        self._store: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    async def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            ts, payload = entry
            if time.time() - ts > self._ttl:
                self._store.pop(key, None)
                self.misses += 1
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

    def size(self) -> int:
        return len(self._store)


def _cache_key(req: ReasoningRequest) -> str:
    """Stable hash of the semantically-relevant request fields."""
    payload = {
        "medicines": sorted(m.lower().strip() for m in req.medicines),
        "symptoms": sorted(s.lower().strip() for s in req.symptoms),
        "disease": (req.disease or "").lower().strip(),
        "diagnosis": (req.diagnosis or "").lower().strip(),
        "age": req.age,
        "gender": (req.gender or "").lower(),
        "include_rag": req.include_rag,
        "run_disease_prediction": req.run_disease_prediction,
        "top_k": req.top_k,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ==========================================================================
# Service
# ==========================================================================
class ClinicalReasoningService:
    """Orchestrates reasoning runs with caching and best-effort persistence."""

    def __init__(self) -> None:
        self._cache = _ReasoningCache(
            settings.CLINICAL_REASONING_CACHE_TTL,
            settings.CLINICAL_REASONING_CACHE_SIZE,
        )

    async def analyze(self, req: ReasoningRequest, *, persist: bool = True) -> ClinicalReasoningReport:
        """Run the reasoning pipeline, serving from cache when possible."""
        key = _cache_key(req)

        if req.use_cache:
            cached = await self._cache.get(key)
            if cached is not None:
                logger.info("Reasoning cache hit (%s…)", key[:10])
                report = ClinicalReasoningReport(**cached)
                report.cached = True
                return report

        report = await get_reasoning_engine().run(req)
        report.cached = False

        # Cache the fresh result (store the un-flagged dump).
        await self._cache.put(key, report.model_dump(mode="json"))

        if persist:
            report.id = await self._save(report, req.source_record_id)
        return report

    # -- persistence -------------------------------------------------------
    async def _save(self, report: ClinicalReasoningReport, source_record_id: str | None) -> str | None:
        """Persist one report. Best-effort: never raises."""
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            report.id = record_id
            leading = report.disease_prediction.leading
            row = ReasoningRecord(
                id=record_id,
                created_at=report.created_at or utcnow(),
                source_record_id=source_record_id,
                leading_disease=leading.disease if leading else None,
                medicine_count=report.patient_summary.medicine_count,
                symptom_count=report.patient_summary.symptom_count,
                step_count=len(report.reasoning_chain),
                risk_level=report.risk_level.value,
                confidence=report.confidence,
                report=report.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info(
                "Saved reasoning report %s (risk=%s, conf=%.1f)",
                record_id, report.risk_level.value, report.confidence,
            )
            return record_id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save reasoning report")
            return None

    # -- history reads -----------------------------------------------------
    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(ReasoningRecord.id))) or 0
            stmt = (
                select(ReasoningRecord)
                .order_by(ReasoningRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return {
            "items": [r.item() for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "pages": (int(total) + page_size - 1) // page_size,
        }

    async def get_history(self, record_id: str) -> dict | None:
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(ReasoningRecord, record_id)
            return row.report if row else None

    async def compute_stats(self) -> dict:
        await _ensure_db()
        async with _Session() as session:
            total = await session.scalar(select(func.count(ReasoningRecord.id))) or 0
            avg = await session.scalar(select(func.avg(ReasoningRecord.confidence)))

            async def _count(level: str) -> int:
                return int(await session.scalar(
                    select(func.count(ReasoningRecord.id)).where(
                        ReasoningRecord.risk_level == level
                    )
                ) or 0)

            return {
                "total_reports": int(total),
                "average_confidence": round(float(avg or 0.0), 1),
                "critical_cases": await _count("critical"),
                "high_risk_cases": await _count("high"),
                "cache_hits": self._cache.hits,
                "cache_size": self._cache.size(),
            }

    async def clear_history(self) -> int:
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(ReasoningRecord.id))) or 0
            await session.execute(delete(ReasoningRecord))
            await session.commit()
        logger.info("Cleared clinical-reasoning history (%d records)", count)
        return int(count)


_SERVICE: ClinicalReasoningService | None = None


def get_service() -> ClinicalReasoningService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ClinicalReasoningService()
    return _SERVICE


async def reason(req: ReasoningRequest, *, persist: bool = True) -> ClinicalReasoningReport:
    """Module-level shortcut around :meth:`ClinicalReasoningService.analyze`."""
    return await get_service().analyze(req, persist=persist)
