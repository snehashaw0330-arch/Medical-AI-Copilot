"""Service layer for the AI Medical Simulation Engine (async).

Owns the cross-cutting concerns the scenario engine stays out of:

* **Orchestration** — always simulates an implicit *baseline* (current
  prescription, no changes) plus every requested variant scenario, runs them
  concurrently, builds the variant-vs-baseline (and A-vs-B) comparisons, and picks
  the safest recommended scenario.
* **Caching** — an in-memory TTL + LRU cache keyed by a stable hash of the
  request, so identical re-runs skip the subsystem fan-out.
* **Persistence** — best-effort async storage of every report for the history
  views (same SQLAlchemy-async contract as the other modules).

Design contract: async everywhere, best-effort integration, best-effort
persistence — a failure in any of these never propagates out of a simulation.
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
from backend.simulation import treatment_engine
from backend.simulation.simulation_engine import get_engine as get_sim_engine
from backend.simulation.schemas import (
    ComparisonDelta,
    Scenario,
    ScenarioResult,
    SimulationHistoryItem,
    SimulationReport,
    SimulationRequest,
    utcnow,
)

logger = logging.getLogger("simulation.service")

Base = declarative_base()


# ==========================================================================
# Persistence model
# ==========================================================================
class SimulationRecord(Base):
    __tablename__ = "simulation_reports"

    id = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source_record_id = Column(String(64), nullable=True)
    medicine_count = Column(Integer, default=0)
    scenario_count = Column(Integer, default=0)
    top_disease = Column(String(255), nullable=True)
    baseline_risk = Column(String(16), default="low", index=True)
    best_scenario = Column(String(255), nullable=True)
    summary = Column(String(1024), default="")
    report = Column(JSON, nullable=False)

    def item(self) -> SimulationHistoryItem:
        return SimulationHistoryItem(
            id=self.id, created_at=self.created_at,
            medicine_count=self.medicine_count or 0,
            scenario_count=self.scenario_count or 0,
            top_disease=self.top_disease,
            baseline_risk=self.baseline_risk or "low",
            best_scenario=self.best_scenario,
            summary=self.summary or "",
        )


_engine = create_async_engine(
    settings.SIMULATION_DB_URL, echo=False, pool_pre_ping=True, future=True
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
        logger.info("Simulation history store ready (%s)",
                    settings.SIMULATION_DB_URL.split("://")[0])


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


def _cache_key(req: SimulationRequest) -> str:
    payload = req.model_dump(mode="json", exclude={"persist", "use_cache", "generate_report"})
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ==========================================================================
# Service
# ==========================================================================
class SimulationService:
    def __init__(self) -> None:
        self._cache = _Cache(settings.SIMULATION_CACHE_TTL, settings.SIMULATION_CACHE_SIZE)

    async def run(self, req: SimulationRequest) -> SimulationReport:
        t0 = time.perf_counter()
        key = _cache_key(req)

        if req.use_cache:
            cached = await self._cache.get(key)
            if cached is not None:
                logger.info("Simulation cache hit (%s…)", key[:10])
                report = SimulationReport(**cached)
                report.cached = True
                if req.persist:
                    report.id = await self._save(report, req)
                return report

        baseline_medicines = treatment_engine.normalise(req.baseline_medicines)
        engine = get_sim_engine()
        warnings: list[str] = []

        # Cap scenario fan-out.
        scenarios = list(req.scenarios[: settings.SIMULATION_MAX_SCENARIOS])
        # Give each scenario a stable id + a friendly default name (A, B, C…).
        for i, sc in enumerate(scenarios):
            sc.id = sc.id or uuid.uuid4().hex[:8]
            if not sc.name or sc.name == "Scenario":
                sc.name = f"Scenario {chr(ord('A') + i)}"

        baseline_scenario = Scenario(id="baseline", name="Baseline (current)")

        # Run baseline + every variant concurrently.
        results = await asyncio.gather(
            engine.run_scenario(
                baseline_medicines=baseline_medicines, base_patient=req.patient,
                scenario=baseline_scenario, include_rag=req.include_rag, is_baseline=True,
            ),
            *[
                engine.run_scenario(
                    baseline_medicines=baseline_medicines, base_patient=req.patient,
                    scenario=sc, include_rag=req.include_rag,
                )
                for sc in scenarios
            ],
        )
        baseline_result: ScenarioResult = results[0]
        variant_results: list[ScenarioResult] = list(results[1:])
        for r in results:
            warnings.extend(r.warnings)

        # Comparisons: each variant vs baseline, plus A-vs-B when exactly two.
        comparisons: list[ComparisonDelta] = [
            engine.compare(baseline_result, v) for v in variant_results
        ]
        if len(variant_results) == 2:
            comparisons.append(engine.compare(variant_results[0], variant_results[1]))

        recommended_id, summary = self._pick_best(baseline_result, variant_results)

        report = SimulationReport(
            created_at=utcnow(),
            duration_ms=round((time.perf_counter() - t0) * 1000.0, 1),
            baseline=baseline_result,
            results=variant_results,
            comparisons=comparisons,
            recommended_scenario_id=recommended_id,
            summary=summary,
            warnings=sorted(set(warnings)),
            sources=self._sources(baseline_result, variant_results),
        )

        await self._cache.put(key, report.model_dump(mode="json"))

        # Optionally persist a durable Medical Report for the recommended scenario.
        if req.generate_report:
            await self._maybe_report(report, req)

        if req.persist:
            report.id = await self._save(report, req)

        logger.info(
            "Simulation complete: %d scenario(s), baseline risk=%s, best=%s (%.0f ms)",
            len(variant_results), baseline_result.risk_level.value,
            recommended_id, report.duration_ms,
        )
        return report

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _pick_best(baseline: ScenarioResult, variants: list[ScenarioResult]) -> tuple[str | None, str]:
        """Choose the safest scenario (lowest composite risk, no new contraindication)."""
        candidates = [baseline, *variants]
        safe = [c for c in candidates if not c.contraindications] or candidates
        best = min(safe, key=lambda c: c.risk_score)
        if best.scenario_id == baseline.scenario_id:
            summary = (
                f"The current treatment (baseline) remains the safest option at composite "
                f"risk {baseline.risk_score:.0f}/100; no simulated change improved on it."
            )
        else:
            summary = (
                f"'{best.scenario_name}' is the safest simulated option at composite risk "
                f"{best.risk_score:.0f}/100 (baseline {baseline.risk_score:.0f}/100)."
            )
        return best.scenario_id, summary

    @staticmethod
    def _sources(baseline: ScenarioResult, variants: list[ScenarioResult]) -> list[str]:
        srcs = {"simulation-engine"}
        for r in [baseline, *variants]:
            if r.drug_interactions:
                srcs.add("drug-interaction-dataset")
            if r.disease_risk.hypotheses:
                srcs.add("disease-prediction-model")
            if r.evidence:
                srcs.add("rag-knowledge-base")
        return sorted(srcs)

    async def _maybe_report(self, report: SimulationReport, req: SimulationRequest) -> None:
        """Generate a durable Medical Report for the recommended scenario (best-effort)."""
        try:
            from backend.report_generator import get_service as get_report_service

            best = next(
                (r for r in [report.baseline, *report.results]
                 if r.scenario_id == report.recommended_scenario_id),
                report.baseline,
            )
            ocr_like = {
                "provider": "simulation-engine",
                "medicines": [{"raw_text": m.label(), "name": m.name, "confidence": 1.0}
                              for m in best.resulting_medicines],
                "fields": {
                    "patient": None,
                    "age": str(best.effective_patient.age) if best.effective_patient.age is not None else None,
                    "gender": best.effective_patient.gender,
                    "diagnosis": best.disease_risk.hypotheses[0].disease if best.disease_risk.hypotheses else None,
                },
                "raw_text": "", "overall_confidence": 1.0, "warnings": [],
                "drug_interactions": best.drug_interactions,
            }
            rid = await get_report_service().generate_from_ocr(
                ocr_like, filename="treatment-simulation", processing_time=0.0, image_src=None,
            )
            best.report_id = rid
        except Exception as exc:  # noqa: BLE001
            logger.warning("Simulation report generation failed: %s", exc)

    # -- persistence -------------------------------------------------------
    async def _save(self, report: SimulationReport, req: SimulationRequest) -> str | None:
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            report.id = record_id
            top = report.baseline.disease_risk.hypotheses
            best_name = None
            for r in [report.baseline, *report.results]:
                if r.scenario_id == report.recommended_scenario_id:
                    best_name = r.scenario_name
            row = SimulationRecord(
                id=record_id, created_at=report.created_at or utcnow(),
                source_record_id=req.source_record_id,
                medicine_count=len(report.baseline.resulting_medicines),
                scenario_count=len(report.results),
                top_disease=top[0].disease if top else None,
                baseline_risk=report.baseline.risk_level.value,
                best_scenario=best_name, summary=report.summary[:1024],
                report=report.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info("Saved simulation %s (%d scenarios)", record_id, len(report.results))
            return record_id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save simulation report")
            return None

    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(SimulationRecord.id))) or 0
            stmt = (
                select(SimulationRecord)
                .order_by(SimulationRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
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
            row = await session.get(SimulationRecord, record_id)
            return row.report if row else None

    async def clear_history(self) -> int:
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(SimulationRecord.id))) or 0
            await session.execute(delete(SimulationRecord))
            await session.commit()
        logger.info("Cleared simulation history (%d records)", count)
        return int(count)


_SERVICE: SimulationService | None = None


def get_service() -> SimulationService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = SimulationService()
    return _SERVICE


async def run_simulation(req: SimulationRequest) -> SimulationReport:
    """Module-level shortcut around :meth:`SimulationService.run`."""
    return await get_service().run(req)
