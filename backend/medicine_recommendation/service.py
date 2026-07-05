"""Business logic + async orchestration for Medicine Recommendation.

Pipeline per request:

    names ─► alternative_finder.resolve (dataset, threaded) ─┐
                                                             ├─► recommendation_engine
    resolved names ─► RAG amedicine_info (knowledge base) ───┘        (pure)
                                                                        │
                                                                        ▼
                                                        RecommendationReport (persisted)

Design contract (identical to the other modules):

* **Async everywhere.** The dataset/index work is CPU/pandas-bound and runs in a
  worker thread via :func:`asyncio.to_thread`; RAG enrichment is awaited. The two
  run concurrently.
* **Best-effort integration.** RAG failure degrades the report gracefully and is
  recorded in ``warnings`` — it never raises out of :meth:`recommend`.
* **Best-effort persistence.** Saving to history never raises, so a DB problem can
  never break a recommendation or the OCR flow that triggered it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.medicine_recommendation import alternative_finder as af
from backend.medicine_recommendation import recommendation_engine as re_engine
from backend.medicine_recommendation.models import Base, RecommendationRecord, utcnow
from backend.medicine_recommendation.schemas import (
    MedicineRecommendation,
    MedicineRecommendRequest,
    RecommendationReport,
)

logger = logging.getLogger("medicine_recommendation")


# ==========================================================================
# Persistence (async; same contract as the other history stores)
# ==========================================================================
_engine = create_async_engine(
    settings.MEDICINE_REC_DB_URL, echo=False, pool_pre_ping=True, future=True
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
            "Medicine-recommendation history store ready (%s)",
            settings.MEDICINE_REC_DB_URL.split("://")[0],
        )


# ==========================================================================
# Service
# ==========================================================================
class MedicineRecommendationService:
    """Orchestrates dataset resolution, RAG enrichment and report assembly."""

    # -- RAG enrichment (reuse the existing module, best-effort) -----------
    async def _rag_enrich(
        self, names: list[str], include_rag: bool, warnings: list[str]
    ) -> dict[str, dict]:
        """Return {lowercased name → rag entry} for the given medicines."""
        if not (include_rag and settings.MEDICINE_REC_USE_RAG and names):
            return {}
        try:
            from backend.rag.rag_service import get_rag_service

            info = await get_rag_service().amedicine_info(names)
            entries = info.get("medicines", []) if isinstance(info, dict) else []
            return {str(e.get("name", "")).strip().lower(): e for e in entries}
        except Exception as exc:  # noqa: BLE001 — RAG is optional enrichment
            logger.debug("RAG medicine enrichment skipped: %s", exc)
            warnings.append("Knowledge-base enrichment was unavailable for this report.")
            return {}

    # -- main --------------------------------------------------------------
    async def recommend(self, req: MedicineRecommendRequest) -> RecommendationReport:
        """Build a full recommendation report for the requested medicines."""
        warnings: list[str] = []
        names = [n.strip() for n in req.medicines if n and n.strip()]
        if not names:
            report = RecommendationReport(
                medicine_count=0, ai_report="No medicines were provided.",
                warnings=["No medicine names were supplied."],
            )
            if req.persist:
                report.id = await self._save(report, req)
            return report

        # 1) Resolve every medicine against the dataset (threaded, concurrent).
        resolved = await asyncio.gather(*(asyncio.to_thread(af.resolve, n) for n in names))

        # 2) RAG enrichment for the resolved names (concurrent with nothing else
        #    now, but kept awaitable + best-effort).
        rag_map = await self._rag_enrich(
            [r.resolved_name for r in resolved], req.include_rag, warnings
        )

        # 3) Assemble each medicine's recommendation (pure).
        recommendations: list[MedicineRecommendation] = []
        all_sources: set[str] = set()
        for r in resolved:
            rag_entry = rag_map.get(r.resolved_name.strip().lower(), {})
            rag_fields = rag_entry.get("fields") if rag_entry else None
            rag_summary = rag_entry.get("summary") if rag_entry else None
            rag_conf = float(rag_entry.get("confidence", 0.0) or 0.0) if rag_entry else 0.0
            rag_sources = rag_entry.get("sources", []) if rag_entry else []
            rag_chunks = rag_entry.get("chunks", []) if rag_entry else []

            info = re_engine.build_drug_info(r, rag_fields)
            generics, brands, similar = re_engine.build_alternatives(r, req.max_alternatives)
            rec = MedicineRecommendation(
                detected_name=r.detected,
                resolved_name=r.resolved_name,
                matched=r.matched,
                match_score=r.score,
                drug_info=info,
                generic_equivalents=generics,
                brand_alternatives=brands,
                similar_medicines=similar,
                warnings=re_engine.build_warnings(info),
                ai_summary=re_engine.build_summary(r, info, generics, brands, similar, rag_summary),
                rag_sources=rag_sources,
                related_documents=re_engine.to_related_documents(rag_chunks),
                confidence_score=re_engine.compute_confidence(r, info, rag_conf),
                notes=(["Not confidently matched to the medicine dataset."] if not r.matched else []),
            )
            recommendations.append(rec)
            all_sources.update(rag_sources)
            if not r.matched:
                warnings.append(f"'{r.detected}' could not be confidently identified.")

        # 4) Overall report.
        overall = round(
            sum(x.confidence_score for x in recommendations) / len(recommendations), 1
        ) if recommendations else 0.0
        sources = ["medicine-dataset"]
        if all_sources:
            sources.append("rag-knowledge-base")
            sources.extend(sorted(all_sources))

        report = RecommendationReport(
            medicines=recommendations,
            medicine_count=len(recommendations),
            overall_confidence=overall,
            ai_report=re_engine.build_ai_report(recommendations),
            sources=sorted(set(sources)),
            warnings=warnings,
        )

        # 5) Persist (best-effort — never raises).
        if req.persist:
            report.id = await self._save(report, req)
        return report

    # -- persistence -------------------------------------------------------
    async def _save(self, report: RecommendationReport, req: MedicineRecommendRequest) -> str | None:
        """Persist one report. Best-effort: never raises."""
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            report.id = record_id
            report.created_at = utcnow()

            names = [r.resolved_name or r.detected_name for r in report.medicines]
            row = RecommendationRecord(
                id=record_id,
                created_at=report.created_at,
                source_record_id=req.source_record_id,
                medicine_names=",".join(n.lower() for n in names if n),
                medicine_count=report.medicine_count,
                overall_confidence=report.overall_confidence,
                report=report.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info(
                "Saved medicine recommendation %s (%d medicine(s), confidence=%.1f)",
                record_id, report.medicine_count, report.overall_confidence,
            )
            return record_id
        except Exception:  # noqa: BLE001 — persistence must never break the report
            logger.exception("Failed to save medicine recommendation")
            return None

    # -- history reads -----------------------------------------------------
    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        """Return a paginated page of past reports (newest first)."""
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(RecommendationRecord.id))) or 0
            stmt = (
                select(RecommendationRecord)
                .order_by(RecommendationRecord.created_at.desc())
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
        """Return the full stored report for one recommendation, or None."""
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(RecommendationRecord, record_id)
            return row.report if row else None

    async def clear_history(self) -> int:
        """Delete every stored report. Returns the number removed."""
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(RecommendationRecord.id))) or 0
            await session.execute(delete(RecommendationRecord))
            await session.commit()
        logger.info("Cleared medicine-recommendation history (%d records)", count)
        return int(count)


# Process-wide singleton.
_SERVICE: MedicineRecommendationService | None = None


def get_service() -> MedicineRecommendationService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MedicineRecommendationService()
    return _SERVICE


# ==========================================================================
# Convenience coroutines used by the OCR pipeline for auto-recommendation.
# ==========================================================================
async def recommend_medicines(req: MedicineRecommendRequest) -> RecommendationReport:
    """Module-level shortcut around :meth:`MedicineRecommendationService.recommend`."""
    return await get_service().recommend(req)


async def recommend_from_ocr(
    ocr_result: dict,
    *,
    persist: bool = True,
    source_record_id: str | None = None,
) -> RecommendationReport:
    """Build a recommendation report from an OCR result dict (Requirement 7)."""
    names: list[str] = []
    for m in ocr_result.get("medicines", []) or []:
        name = (m.get("name") or m.get("raw_text") or "").strip()
        if name:
            names.append(name)
    req = MedicineRecommendRequest(
        medicines=names, include_rag=True, persist=persist,
        source_record_id=source_record_id,
    )
    return await get_service().recommend(req)


__all__ = [
    "MedicineRecommendationService",
    "get_service",
    "recommend_medicines",
    "recommend_from_ocr",
]
