"""Business logic + async orchestration for the Symptom Checker & Triage module.

This is the "brain" that assembles a unified triage assessment from the
project's existing subsystems and the deterministic triage engine:

    symptoms ─► SymptomMatcher ─► categories ─┐
             └─► Disease Prediction (ML) ──────┼─► Triage Engine ─► urgency,
    disease + symptoms ─► RAG Knowledge Base ──┘      specialist, tests,
                                                      home care, red flags
                                                              │
                                                              ▼
                                                    TriageAssessment (persisted)

Design contract (identical to the other modules):

* **Async everywhere.** CPU-bound work (disease-model inference) runs in a worker
  thread via :func:`asyncio.to_thread`; the event loop is never blocked. Disease
  prediction and RAG retrieval run concurrently.
* **Best-effort integration.** Every external call (disease model, RAG) is wrapped
  so a failure degrades the assessment gracefully and is recorded in ``warnings``
  — it never raises out of :meth:`SymptomCheckerService.analyze`.
* **Best-effort persistence.** Saving to history never raises, so a DB problem can
  never break an assessment.
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
from backend.symptom_checker import triage_engine as te
from backend.symptom_checker.models import AssessmentRecord, Base, utcnow
from backend.symptom_checker.schemas import (
    ConditionHypothesis,
    DurationOption,
    RelatedDocument,
    SymptomAnalysisRequest,
    SymptomCatalog,
    SymptomCategory,
    SymptomResolution,
    TriageAssessment,
)
from backend.symptom_checker.symptom_matcher import (
    CATALOG,
    CATEGORY_LABELS,
    DURATIONS,
    get_matcher,
)

logger = logging.getLogger("symptom_checker")


# ==========================================================================
# Persistence (async; same contract as the other history stores)
# ==========================================================================
_engine = create_async_engine(
    settings.SYMPTOM_DB_URL, echo=False, pool_pre_ping=True, future=True
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
            "Symptom-checker history store ready (%s)",
            settings.SYMPTOM_DB_URL.split("://")[0],
        )


# ==========================================================================
# Service
# ==========================================================================
class SymptomCheckerService:
    """Orchestrates symptom resolution, disease prediction, RAG and triage."""

    # -- disease prediction (reuse the existing model, best-effort) --------
    async def _predict(
        self, symptoms: list[str], top_k: int, warnings: list[str]
    ) -> tuple[list[ConditionHypothesis], str]:
        """Run the disease-prediction model. Returns (conditions, confidence_level)."""
        if not symptoms:
            return [], "low"
        try:
            from backend.disease.service import get_service as get_disease_service

            svc = get_disease_service()
            # Model inference is synchronous/CPU-bound → run off the event loop.
            response = await asyncio.to_thread(svc.predict, symptoms, top_k)
            conditions = [
                ConditionHypothesis(
                    disease=p.disease,
                    confidence=p.confidence,
                    explanation=p.explanation,
                    matched_symptoms=p.matched_symptoms,
                    source="disease-model",
                )
                for p in response.predictions
            ]
            for w in response.warnings:
                warnings.append(w)
            return conditions, response.confidence_level
        except Exception as exc:  # noqa: BLE001 — prediction is best-effort enrichment
            logger.warning("Disease prediction unavailable: %s", exc)
            warnings.append("Condition prediction was unavailable for this assessment.")
            return [], "low"

    # -- RAG enrichment (optional, best-effort) ----------------------------
    async def _rag(
        self,
        symptoms: list[str],
        conditions: list[ConditionHypothesis],
        include_rag: bool,
        warnings: list[str],
    ) -> tuple[str | None, list[RelatedDocument], list[str]]:
        """Retrieve evidence-based context. Returns (narrative, docs, sources)."""
        if not (include_rag and settings.SYMPTOM_USE_RAG):
            return None, [], []
        try:
            from backend.rag.rag_service import get_rag_service

            topic = conditions[0].disease if conditions else ""
            sym = ", ".join(symptoms[:6])
            question = (
                f"What are the causes, warning signs and recommended care for "
                f"{topic or 'these symptoms'}"
                + (f" in a patient reporting {sym}" if sym else "")
            ).strip()
            info = await get_rag_service().aquery(question)
            if not isinstance(info, dict) or info.get("provider") == "unavailable":
                return None, [], []
            answer = info.get("answer")
            sources = info.get("sources", []) or []
            docs = [
                RelatedDocument(
                    source=c.get("source", "knowledge-base"),
                    excerpt=(c.get("text", "") or "")[:400],
                    score=float(c.get("score", 0.0) or 0.0),
                )
                for c in (info.get("chunks", []) or [])[:4]
            ]
            return answer, docs, sources
        except Exception as exc:  # noqa: BLE001 — RAG is optional enrichment
            logger.debug("RAG enrichment skipped: %s", exc)
            warnings.append("Knowledge-base references were unavailable for this assessment.")
            return None, [], []

    # -- main --------------------------------------------------------------
    async def analyze(self, req: SymptomAnalysisRequest) -> TriageAssessment:
        """Run the full symptom-checker & triage assessment."""
        warnings: list[str] = []

        # 1) Resolve symptoms against the categorized catalog (cheap, synchronous).
        matcher = get_matcher()
        matches = matcher.match_many(req.symptoms)
        resolved = [
            SymptomResolution(
                input=m.input, matched=m.matched, category=m.category,
                score=round(m.score, 1),
            )
            for m in matches
        ]
        canonical = [m.matched for m in matches if m.matched]
        categories = [m.category for m in matches if m.matched]
        unmatched = [m.input for m in matches if not m.matched]
        if not canonical:
            warnings.append(
                "None of the symptoms were recognised — try rephrasing or picking "
                "from the categorized list."
            )

        # 2) Disease prediction + 3) RAG run concurrently (independent).
        (conditions, confidence_level), (rag_answer, rag_docs, rag_sources) = (
            await asyncio.gather(
                self._predict(canonical or req.symptoms, req.top_k, warnings),
                self._rag(canonical or req.symptoms, [], req.include_rag, warnings),
            )
        )

        # 4) Deterministic triage (pure, CPU-cheap).
        red_flags = te.detect_red_flags(canonical)
        category = te.dominant_category(categories)
        score = te.compute_triage_score(req.severity, red_flags, req.duration, conditions)
        urgency = te.grade_urgency(score, red_flags)
        severity_level = te.grade_severity(req.severity, red_flags, score)
        specialist = te.recommend_specialist(category, conditions)
        tests = te.build_tests(category, conditions)
        home_care = te.build_home_care(category, urgency)
        warning_msg = te.emergency_warning(red_flags, urgency)
        label, description = te.URGENCY_META[urgency]

        # 5) Provenance.
        sources = ["symptom-triage-engine"]
        if conditions:
            sources.append("disease-prediction-model")
        if rag_sources:
            sources.extend(rag_sources)

        assessment = TriageAssessment(
            symptoms=canonical,
            resolved_symptoms=resolved,
            unmatched_symptoms=unmatched,
            severity_input=req.severity,
            duration=req.duration,
            age=req.age,
            gender=req.gender,
            possible_conditions=conditions,
            confidence_level=confidence_level,
            severity_level=severity_level,
            urgency_level=urgency,
            urgency_label=label,
            urgency_description=description,
            triage_score=score,
            recommended_specialist=specialist,
            recommended_tests=tests,
            home_care=home_care,
            red_flags=red_flags,
            emergency_warning=warning_msg,
            rag_explanation=rag_answer,
            related_documents=rag_docs,
            rag_sources=rag_sources,
            warnings=warnings,
            sources=sorted(set(sources)),
        )

        # 6) Persist (best-effort — never raises).
        if req.persist:
            assessment.id = await self._save(assessment)

        return assessment

    # -- persistence -------------------------------------------------------
    async def _save(self, assessment: TriageAssessment) -> str | None:
        """Persist one assessment. Best-effort: never raises."""
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            assessment.id = record_id
            assessment.created_at = utcnow()

            top = assessment.possible_conditions[0].disease if assessment.possible_conditions else None
            row = AssessmentRecord(
                id=record_id,
                created_at=assessment.created_at,
                symptom_names=",".join(s.lower() for s in assessment.symptoms),
                symptom_count=len(assessment.symptoms),
                severity_input=assessment.severity_input,
                duration=assessment.duration,
                top_condition=top,
                urgency_level=assessment.urgency_level.value,
                severity_level=assessment.severity_level.value,
                triage_score=assessment.triage_score,
                report=assessment.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info(
                "Saved symptom assessment %s (urgency=%s, score=%.1f, %d red flag(s))",
                record_id, assessment.urgency_level.value, assessment.triage_score,
                len(assessment.red_flags),
            )
            return record_id
        except Exception:  # noqa: BLE001 — persistence must never break the assessment
            logger.exception("Failed to save symptom assessment")
            return None

    # -- history reads -----------------------------------------------------
    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        """Return a paginated page of past assessments (newest first)."""
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(AssessmentRecord.id))) or 0
            stmt = (
                select(AssessmentRecord)
                .order_by(AssessmentRecord.created_at.desc())
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
        """Return the full stored report for one assessment, or None if missing."""
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(AssessmentRecord, record_id)
            return row.report if row else None

    async def clear_history(self) -> int:
        """Delete every stored assessment. Returns the number removed."""
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(AssessmentRecord.id))) or 0
            await session.execute(delete(AssessmentRecord))
            await session.commit()
        logger.info("Cleared symptom-checker history (%d records)", count)
        return int(count)

    # -- catalog (Requirements 2 & 3) --------------------------------------
    def catalog(self) -> SymptomCatalog:
        """The categorized symptom catalog + duration options for the UI."""
        categories = [
            SymptomCategory(key=key, label=CATEGORY_LABELS[key], symptoms=symptoms)
            for key, symptoms in CATALOG.items()
        ]
        total = sum(len(c.symptoms) for c in categories)
        durations = [DurationOption(key=k, label=lbl) for k, lbl in DURATIONS]
        return SymptomCatalog(categories=categories, durations=durations, total_symptoms=total)


# Process-wide singleton.
_SERVICE: SymptomCheckerService | None = None


def get_service() -> SymptomCheckerService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = SymptomCheckerService()
    return _SERVICE


# Convenience coroutine (kept symmetrical with the other modules).
async def analyze_symptoms(req: SymptomAnalysisRequest) -> TriageAssessment:
    """Module-level shortcut around :meth:`SymptomCheckerService.analyze`."""
    return await get_service().analyze(req)


__all__ = ["SymptomCheckerService", "get_service", "analyze_symptoms"]
