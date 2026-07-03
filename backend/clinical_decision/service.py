"""Business logic + async orchestration for Clinical Decision Support.

This is the "brain" that assembles a unified clinical report from every other
subsystem the project already has:

    symptoms ─────────────► Disease Prediction ─┐
    medicines (OCR/typed) ─► Drug Interactions ──┤
    disease + medicines ───► RAG Knowledge Base ─┼──► Rules Engine ──► Risk
                                                 │        │            Analyzer
                                                 │        ▼               │
                                                 └──► Recommendation ◄────┘
                                                        Engine
                                                          │
                                                          ▼
                                                   ClinicalReport (persisted)

Design contract (identical to the other modules):

* **Async everywhere.** CPU-bound work (disease model inference) runs in a worker
  thread via :func:`asyncio.to_thread`; the event loop is never blocked.
* **Best-effort integration.** Every external call (disease model, interactions,
  RAG) is wrapped so a failure degrades the report gracefully and is recorded in
  ``warnings`` — it never raises out of :meth:`ClinicalDecisionService.analyze`.
* **Best-effort persistence.** Saving to history never raises, so a DB problem can
  never break the analysis or the OCR flow that triggered it.
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

from backend.clinical_decision import recommendation_engine as rec
from backend.clinical_decision import risk_analyzer
from backend.clinical_decision.models import Base, ClinicalRecord, utcnow
from backend.clinical_decision.rules_engine import ClinicalContext, evaluate
from backend.clinical_decision.schemas import (
    ClinicalAnalysisRequest,
    ClinicalReport,
    DiseaseHypothesis,
)
from backend.config import settings

logger = logging.getLogger("clinical_decision")


# ==========================================================================
# Persistence (async; same contract as the OCR-history / interaction stores)
# ==========================================================================
_engine = create_async_engine(
    settings.CLINICAL_DB_URL, echo=False, pool_pre_ping=True, future=True
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
            "Clinical-decision history store ready (%s)",
            settings.CLINICAL_DB_URL.split("://")[0],
        )


# ==========================================================================
# Service
# ==========================================================================
class ClinicalDecisionService:
    """Orchestrates the full clinical analysis across the project's subsystems."""

    # -- disease prediction (optional, best-effort) ------------------------
    async def _predict_disease(
        self, req: ClinicalAnalysisRequest, warnings: list[str]
    ) -> list[DiseaseHypothesis]:
        """Return disease hypotheses from the input and/or the ML model."""
        hypotheses: list[DiseaseHypothesis] = []

        # An explicit disease / diagnosis from the caller is always trusted first.
        if req.disease:
            hypotheses.append(DiseaseHypothesis(
                disease=req.disease, confidence=100.0,
                explanation="Provided by the caller.", source="input"))
        elif req.diagnosis:
            hypotheses.append(DiseaseHypothesis(
                disease=req.diagnosis, confidence=100.0,
                explanation="Parsed from the prescription diagnosis.",
                source="diagnosis"))

        # Run the ML model from symptoms when enabled and no disease was given.
        should_predict = (
            req.run_disease_prediction
            and settings.CLINICAL_PREDICT_DISEASE
            and req.symptoms
            and not hypotheses
        )
        if not should_predict:
            return hypotheses

        try:
            from backend.disease.service import get_service as get_disease_service

            svc = get_disease_service()
            response = await asyncio.to_thread(svc.predict, req.symptoms, 3)
            for p in response.predictions:
                hypotheses.append(DiseaseHypothesis(
                    disease=p.disease, confidence=p.confidence,
                    explanation=p.explanation, source="model"))
            if not response.predictions:
                warnings.append(
                    "The symptoms provided were not recognised by the disease model."
                )
        except Exception as exc:  # noqa: BLE001 — prediction is optional enrichment
            logger.warning("Disease prediction unavailable: %s", exc)
            warnings.append("Disease prediction was unavailable for this analysis.")
        return hypotheses

    # -- drug interactions (reuse the existing module) ---------------------
    async def _interactions(
        self,
        req: ClinicalAnalysisRequest,
        precomputed: dict | None,
        warnings: list[str],
    ) -> dict | None:
        """Return the drug-interaction sub-report (reusing one if supplied)."""
        names = [m.strip() for m in req.medicines if m and m.strip()]
        if precomputed:  # e.g. the OCR flow already ran this — don't repeat it.
            return precomputed
        if len(names) < 2:
            return None
        try:
            from backend.drug_interactions import analyze_medicines

            report = await analyze_medicines(
                names,
                include_rag=req.include_rag,
                persist=False,  # the clinical record is the system of record here
                source_record_id=req.source_record_id,
            )
            return report.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 — interactions are best-effort
            logger.warning("Drug-interaction analysis unavailable: %s", exc)
            warnings.append("Drug-interaction analysis was unavailable for this report.")
            return None

    # -- RAG enrichment (optional, best-effort) ----------------------------
    async def _rag_context(
        self,
        req: ClinicalAnalysisRequest,
        diseases: list[DiseaseHypothesis],
        warnings: list[str],
    ) -> tuple[str | None, list[str], float]:
        """Retrieve knowledge-base context. Returns (notes, sources, confidence)."""
        if not (req.include_rag and settings.CLINICAL_USE_RAG):
            return None, [], 0.5
        try:
            from backend.rag.rag_service import get_rag_service

            topic = (diseases[0].disease if diseases else req.diagnosis) or ""
            meds = ", ".join(req.medicines[:6])
            question = (
                f"Clinical considerations, monitoring and precautions for "
                f"{topic or 'the prescribed medicines'}"
                + (f" with medications {meds}" if meds else "")
            ).strip()
            info = await get_rag_service().aquery(question)
            answer = info.get("answer") if isinstance(info, dict) else None
            sources = info.get("sources", []) if isinstance(info, dict) else []
            confidence = float(info.get("confidence", 0.0) or 0.0) if isinstance(info, dict) else 0.0
            # Treat the canned "unavailable" answer as no enrichment.
            if info.get("provider") == "unavailable":
                return None, [], 0.5
            return answer, sources, confidence
        except Exception as exc:  # noqa: BLE001 — RAG is optional enrichment
            logger.debug("RAG enrichment skipped: %s", exc)
            return None, [], 0.5

    # -- main --------------------------------------------------------------
    async def analyze(
        self,
        req: ClinicalAnalysisRequest,
        *,
        interaction_report: dict | None = None,
    ) -> ClinicalReport:
        """Run the full clinical decision-support analysis.

        ``interaction_report`` lets a caller (e.g. the OCR flow) pass an
        already-computed drug-interaction report so it is not recomputed.
        """
        warnings: list[str] = []

        # 1) Disease hypotheses (input + ML model) and 2) drug interactions run
        #    concurrently — they are independent.
        diseases, interactions = await asyncio.gather(
            self._predict_disease(req, warnings),
            self._interactions(req, interaction_report, warnings),
        )
        interactions = interactions or {}

        # 3) RAG context (needs the leading disease hypothesis for its query).
        rag_notes, rag_sources, rag_conf = await self._rag_context(req, diseases, warnings)

        # 4) Build the reasoning context from everything gathered.
        resolved = interactions.get("resolved_medicines", []) or []
        unmatched = interactions.get("unmatched_medicines", []) or []
        ctx = ClinicalContext(
            age=req.age,
            gender=req.gender,
            symptoms=[s.strip() for s in req.symptoms if s and s.strip()],
            disease=diseases[0].disease if diseases else req.disease,
            diagnosis=req.diagnosis,
            medicines=[m.strip() for m in req.medicines if m and m.strip()],
            resolved_medicines=resolved,
            unmatched_medicines=unmatched,
            interaction_report=interactions,
        )

        # 5) Rules → 6) risk → 7) recommendations (all pure, CPU-cheap).
        findings = evaluate(ctx)
        risk_level, risk_score = risk_analyzer.assess(findings, interactions)
        next_steps = rec.build_next_steps(findings, risk_level)
        follow_up = rec.build_follow_up(findings, risk_level)
        summary = rec.build_summary(ctx, findings, diseases, risk_level, interactions)
        confidence = rec.compute_confidence(ctx, diseases, interactions, rag_conf)

        # 8) Provenance.
        sources = ["clinical-rules-engine"]
        if diseases and any(d.source == "model" for d in diseases):
            sources.append("disease-prediction-model")
        if interactions.get("interactions") or interactions.get("warnings"):
            sources.append("drug-interaction-dataset")
        if rag_sources:
            sources.extend(rag_sources)

        report = ClinicalReport(
            medicines=ctx.medicines,
            resolved_medicines=resolved,
            unmatched_medicines=unmatched,
            symptoms=ctx.symptoms,
            age=req.age,
            gender=req.gender,
            clinical_summary=summary,
            disease_prediction=diseases,
            possible_risks=findings.possible_risks,
            red_flags=findings.red_flags,
            contraindications=findings.contraindications,
            missing_information=findings.missing_information,
            recommended_next_steps=next_steps,
            recommended_lab_tests=findings.recommended_lab_tests,
            follow_up=follow_up,
            drug_interactions=interactions or None,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_counts=risk_analyzer.red_flag_counts(findings.red_flags),
            confidence=confidence,
            sources=sorted(set(sources)),
            rag_notes=rag_notes,
            rag_sources=rag_sources,
            warnings=warnings,
        )

        # 9) Persist (best-effort — never raises).
        if req.persist:
            report.id = await self._save(report, req.source_record_id)

        return report

    # -- persistence -------------------------------------------------------
    async def _save(self, report: ClinicalReport, source_record_id: str | None) -> str | None:
        """Persist one analysis. Best-effort: never raises."""
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            report.id = record_id
            report.created_at = utcnow()

            top_disease = report.disease_prediction[0].disease if report.disease_prediction else None
            row = ClinicalRecord(
                id=record_id,
                created_at=report.created_at,
                source_record_id=source_record_id,
                medicines=report.medicines,
                medicine_names=",".join(n.lower() for n in report.medicines),
                medicine_count=len(report.medicines),
                top_disease=top_disease,
                risk_level=report.risk_level.value,
                risk_score=report.risk_score,
                red_flag_count=len(report.red_flags),
                summary=report.clinical_summary,
                report=report.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info(
                "Saved clinical analysis %s (risk=%s, score=%.1f, %d red flags)",
                record_id, report.risk_level.value, report.risk_score, len(report.red_flags),
            )
            return record_id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save clinical analysis")
            return None

    # -- history reads -----------------------------------------------------
    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        """Return a paginated page of past analyses (newest first)."""
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(ClinicalRecord.id))) or 0
            stmt = (
                select(ClinicalRecord)
                .order_by(ClinicalRecord.created_at.desc())
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
        """Return the full stored report for one analysis, or None if missing."""
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(ClinicalRecord, record_id)
            return row.report if row else None

    async def compute_stats(self) -> dict:
        """Aggregate risk-level counts for the dashboard cards (Requirement 8)."""
        await _ensure_db()
        async with _Session() as session:
            total = await session.scalar(select(func.count(ClinicalRecord.id))) or 0
            avg = await session.scalar(select(func.avg(ClinicalRecord.risk_score)))

            async def _count(level: str) -> int:
                return int(await session.scalar(
                    select(func.count(ClinicalRecord.id)).where(
                        ClinicalRecord.risk_level == level
                    )
                ) or 0)

            return {
                "total_reports": int(total),
                "critical_cases": await _count("critical"),
                "high_risk_cases": await _count("high"),
                "moderate_risk_cases": await _count("moderate"),
                "low_risk_cases": await _count("low"),
                "average_risk_score": round(float(avg or 0.0), 1),
            }

    async def clear_history(self) -> int:
        """Delete every stored analysis. Returns the number removed."""
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(ClinicalRecord.id))) or 0
            await session.execute(delete(ClinicalRecord))
            await session.commit()
        logger.info("Cleared clinical-decision history (%d records)", count)
        return int(count)


# Process-wide singleton.
_SERVICE: ClinicalDecisionService | None = None


def get_service() -> ClinicalDecisionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ClinicalDecisionService()
    return _SERVICE


# Convenience coroutine used by the OCR pipeline for auto-analysis.
async def analyze_clinical(
    req: ClinicalAnalysisRequest,
    *,
    interaction_report: dict | None = None,
) -> ClinicalReport:
    """Module-level shortcut around :meth:`ClinicalDecisionService.analyze`."""
    return await get_service().analyze(req, interaction_report=interaction_report)
