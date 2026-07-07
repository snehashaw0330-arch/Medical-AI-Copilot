"""Decision tracker — persist, derive, search and aggregate AI decision traces.

The trace store is the system of record for governance. It is populated two ways:

* **Real-time** — the OCR pipeline calls :meth:`record_from_ocr` after an
  analysis, capturing the live decision as it happens (best-effort, non-blocking).
* **Derived / backfill** — :meth:`sync_from_reports` folds the existing Medical
  Report store (read-only) into traces, so every historical analysis is governed
  without re-running it. Idempotent on ``source_report_id``.

Both paths converge on one reproducible :class:`DecisionTrace`, stamped with the
current version set. The tracker also serves the search surface (by patient,
medicine, disease, date, model/dataset version, confidence, status) and the
dashboard aggregation.

Reads the reports DB through its own read-only async engine — it changes nothing
in the existing stores, mirroring the Digital Twin's non-invasive design.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.ai_governance.models import DecisionTraceRecord, utcnow
from backend.ai_governance.schemas import (
    DecisionPage,
    DecisionStatus,
    DecisionTrace,
    DecisionTraceItem,
    RetrievedChunk,
    SyncResult,
    TracedMedicine,
    VersionInfo,
)
from backend.ai_governance.version_manager import VersionManager
from backend.config import settings
from backend.report_generator.models import ReportRecord  # read-only reuse

logger = logging.getLogger("ai_governance")


def _slugify(name: str | None) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"


class DecisionTracker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        ensure_db,
        versions: VersionManager,
    ) -> None:
        self._Session = session_factory
        self._ensure_db = ensure_db
        self._versions = versions
        # Read-only view of the reports store (own engine, like Digital Twin).
        self._reports_engine = create_async_engine(
            settings.REPORTS_DB_URL, echo=False, pool_pre_ping=True, future=True
        )
        self._ReportsSession = async_sessionmaker(
            self._reports_engine, expire_on_commit=False, class_=AsyncSession
        )

    # ---- trace construction ------------------------------------------------
    def _version_info(self) -> VersionInfo:
        return VersionInfo(**self._versions.as_dict())

    def _synth_prompt(self, patient: str | None, meds: list[str], disease: str | None) -> str:
        """Reconstruct the reasoning prompt used to ground the recommendation."""
        meds_txt = ", ".join(meds[:8]) if meds else "the detected medicines"
        return (
            "You are a clinical decision-support assistant. Given the OCR-extracted "
            f"prescription for {patient or 'the patient'} with medicines: {meds_txt}"
            + (f"; leading condition: {disease}" if disease else "")
            + ". Assess drug interactions, validate the prescription, retrieve "
            "supporting evidence from the knowledge base, and produce grounded, "
            "safety-checked recommendations with citations."
        )

    def _derive_status(self, content: dict, confidence: float) -> DecisionStatus:
        if content.get("error"):
            return DecisionStatus.FAILED
        if not content.get("medicines"):
            return DecisionStatus.PARTIAL
        if confidence and confidence < settings.MIN_CONFIDENCE:
            return DecisionStatus.LOW_CONFIDENCE
        # Missing a downstream stage → partial.
        if not (content.get("clinical") or content.get("disease_prediction")):
            return DecisionStatus.PARTIAL
        return DecisionStatus.SUCCESS

    def _trace_from_content(
        self, *, trace_id: str, created_at: datetime, source_report_id: str | None,
        content: dict, processing_time: float,
    ) -> DecisionTrace:
        patient = content.get("patient") or {}
        patient_name = patient.get("name")
        meds_raw = content.get("medicines") or []
        medicines = [
            TracedMedicine(
                name=m.get("name"), raw_text=m.get("raw_text") or "",
                confidence=float(m.get("confidence") or 0.0),
                dosage=m.get("dosage"), matched=bool(m.get("name")),
                candidates=m.get("candidates") or [],
            )
            for m in meds_raw if isinstance(m, dict)
        ]
        disease_pred = content.get("disease_prediction") or []
        top_disease = (
            (disease_pred[0].get("disease") if disease_pred and isinstance(disease_pred[0], dict) else None)
            or patient.get("diagnosis")
        )
        clinical = content.get("clinical")
        interactions = content.get("drug_interactions")
        rag_docs = [
            RetrievedChunk(source=d.get("source", ""), text=(d.get("text") or "")[:600],
                           score=float(d.get("score") or 0.0))
            for d in (content.get("rag_documents") or []) if isinstance(d, dict)
        ]
        recommendations = content.get("recommendations") or (
            (clinical or {}).get("recommended_next_steps") or [])
        confidence = float(content.get("overall_confidence") or 0.0)
        med_names = [m.name for m in medicines if m.name]
        warnings = list(content.get("warnings") or [])
        errors = [content["error"]] if content.get("error") else []

        return DecisionTrace(
            trace_id=trace_id, created_at=created_at, source_report_id=source_report_id,
            patient_id=_slugify(patient_name), patient_name=patient_name,
            ocr_text=(content.get("raw_text") or "")[:4000],
            ocr_provider=content.get("provider") or content.get("engine"),
            ocr_confidence=confidence,
            medicines=medicines, disease_prediction=disease_pred, top_disease=top_disease,
            confidence=confidence,
            drug_interaction=interactions, clinical_decision=clinical,
            prompt=self._synth_prompt(patient_name, med_names, top_disease),
            rag_documents=rag_docs,
            final_recommendation=[r for r in recommendations if isinstance(r, str)][:12],
            execution_time=float(processing_time or content.get("processing_time") or 0.0),
            status=self._derive_status(content, confidence),
            warnings=warnings, errors=errors, versions=self._version_info(),
        )

    # ---- persistence -------------------------------------------------------
    async def _save(self, trace: DecisionTrace) -> None:
        await self._ensure_db()
        async with self._Session() as session:
            row = await session.get(DecisionTraceRecord, trace.trace_id)
            if row is None:
                row = DecisionTraceRecord(trace_id=trace.trace_id)
                session.add(row)
            row.created_at = trace.created_at
            row.source_report_id = trace.source_report_id
            row.patient_id = trace.patient_id
            row.patient_name = trace.patient_name
            row.medicine_names = ", ".join(m.name for m in trace.medicines if m.name)
            row.medicine_count = len(trace.medicines)
            row.top_disease = trace.top_disease
            row.confidence = trace.confidence
            row.status = trace.status.value
            row.execution_time = trace.execution_time
            row.model_version = trace.versions.model_version
            row.dataset_version = trace.versions.dataset_version
            row.trace = trace.model_dump(mode="json")
            await session.commit()

    async def record_from_ocr(
        self, ocr_result: dict, *, processing_time: float = 0.0,
        source_report_id: str | None = None,
    ) -> DecisionTrace:
        """Build + persist a live trace from an OCR analysis result (real-time hook)."""
        # The OCR result carries nested sub-reports under different keys than a
        # stored report; normalise into the report-content shape the builder reads.
        fields = ocr_result.get("fields") or {}
        content = {
            "patient": {
                "name": fields.get("patient_name") or fields.get("name"),
                "age": fields.get("age"), "gender": fields.get("gender"),
                "diagnosis": fields.get("diagnosis"),
            },
            "raw_text": ocr_result.get("raw_text") or ocr_result.get("text") or "",
            "provider": ocr_result.get("provider") or ocr_result.get("engine"),
            "medicines": ocr_result.get("medicines") or [],
            "overall_confidence": ocr_result.get("overall_confidence") or 0.0,
            "disease_prediction": (ocr_result.get("clinical_report") or {}).get("disease_prediction") or [],
            "drug_interactions": ocr_result.get("drug_interactions"),
            "clinical": ocr_result.get("clinical_report"),
            "recommendations": (ocr_result.get("clinical_report") or {}).get("recommended_next_steps") or [],
            "rag_documents": (ocr_result.get("drug_interactions") or {}).get("rag_documents") or [],
            "warnings": ocr_result.get("warnings") or [],
        }
        trace = self._trace_from_content(
            trace_id=f"trace-{uuid.uuid4().hex[:16]}", created_at=utcnow(),
            source_report_id=source_report_id or ocr_result.get("report_id"),
            content=content, processing_time=processing_time,
        )
        await self._save(trace)
        return trace

    # ---- backfill from the reports store -----------------------------------
    async def sync_from_reports(self) -> SyncResult:
        """Import every report not yet traced. Idempotent on source_report_id."""
        started = time.perf_counter()
        await self._ensure_db()
        # Which report ids are already traced?
        async with self._Session() as session:
            traced_ids = set((await session.execute(
                select(DecisionTraceRecord.source_report_id)
                .where(DecisionTraceRecord.source_report_id.is_not(None))
            )).scalars().all())

        try:
            async with self._ReportsSession() as session:
                rows = (await session.execute(
                    select(ReportRecord).order_by(ReportRecord.created_at.asc())
                )).scalars().all()
        except OperationalError:
            # The report store has no table yet (no OCR analysis has run). That is
            # a valid empty state, not an error — governance simply has nothing to
            # backfill until the first report exists.
            logger.info("Report store not initialised yet — nothing to backfill.")
            rows = []

        imported = 0
        skipped = 0
        for row in rows:
            if row.id in traced_ids:
                skipped += 1
                continue
            try:
                trace = self._trace_from_content(
                    trace_id=f"trace-{row.id}", created_at=row.created_at,
                    source_report_id=row.id, content=row.content or {},
                    processing_time=row.processing_time,
                )
                await self._save(trace)
                imported += 1
            except Exception:  # noqa: BLE001 — one bad report never stops the sync
                logger.exception("Failed to derive trace from report %s", row.id)

        async with self._Session() as session:
            total = (await session.execute(
                select(func.count(DecisionTraceRecord.trace_id))
            )).scalar_one()

        return SyncResult(
            imported=imported, skipped=skipped, total_traces=total,
            took_ms=round((time.perf_counter() - started) * 1000, 1),
            message=f"Imported {imported} new trace(s) from the report store.",
        )

    async def _autosync_if_empty(self) -> None:
        """First-read convenience: populate traces from reports if the store is empty."""
        await self._ensure_db()
        async with self._Session() as session:
            any_trace = (await session.execute(
                select(DecisionTraceRecord.trace_id).limit(1)
            )).scalars().first()
        if any_trace is None:
            await self.sync_from_reports()

    # ---- reads / search ----------------------------------------------------
    async def get(self, trace_id: str) -> DecisionTrace | None:
        await self._ensure_db()
        async with self._Session() as session:
            row = await session.get(DecisionTraceRecord, trace_id)
        if row is None:
            return None
        return DecisionTrace.model_validate(row.trace)

    async def search(
        self, *, patient: str | None = None, medicine: str | None = None,
        disease: str | None = None, prediction: str | None = None,
        status: str | None = None, model_version: str | None = None,
        dataset_version: str | None = None, min_confidence: float | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
        page: int = 1, page_size: int = 20,
    ) -> DecisionPage:
        await self._autosync_if_empty()
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        conds = []
        if patient:
            conds.append(DecisionTraceRecord.patient_name.ilike(f"%{patient}%"))
        if medicine:
            conds.append(DecisionTraceRecord.medicine_names.ilike(f"%{medicine}%"))
        # "disease" and "prediction" both filter on the top disease/prediction.
        for term in (disease, prediction):
            if term:
                conds.append(DecisionTraceRecord.top_disease.ilike(f"%{term}%"))
        if status:
            conds.append(DecisionTraceRecord.status == status)
        if model_version:
            conds.append(DecisionTraceRecord.model_version.ilike(f"%{model_version}%"))
        if dataset_version:
            conds.append(DecisionTraceRecord.dataset_version.ilike(f"%{dataset_version}%"))
        if min_confidence is not None:
            conds.append(DecisionTraceRecord.confidence >= min_confidence)
        if date_from:
            conds.append(DecisionTraceRecord.created_at >= date_from)
        if date_to:
            conds.append(DecisionTraceRecord.created_at <= date_to)

        async with self._Session() as session:
            total = (await session.execute(
                select(func.count(DecisionTraceRecord.trace_id)).where(*conds)
            )).scalar_one()
            rows = (await session.execute(
                select(DecisionTraceRecord).where(*conds)
                .order_by(DecisionTraceRecord.created_at.desc())
                .offset((page - 1) * page_size).limit(page_size)
            )).scalars().all()

        items = [DecisionTraceItem(**r.item()) for r in rows]
        pages = (total + page_size - 1) // page_size
        return DecisionPage(items=items, total=total, page=page, page_size=page_size, pages=pages)

    async def all_traces(self, limit: int = 5000) -> list[DecisionTraceRecord]:
        await self._autosync_if_empty()
        async with self._Session() as session:
            return list((await session.execute(
                select(DecisionTraceRecord)
                .order_by(DecisionTraceRecord.created_at.desc()).limit(limit)
            )).scalars().all())

    # ---- dashboard aggregation --------------------------------------------
    async def dashboard(self) -> dict[str, Any]:
        await self._autosync_if_empty()
        async with self._Session() as session:
            rows = (await session.execute(select(DecisionTraceRecord))).scalars().all()

        total = len(rows)
        if total == 0:
            return {
                "total_decisions": 0, "average_confidence": 0.0,
                "average_processing_time": 0.0, "failed_predictions": 0,
                "low_confidence_cases": 0, "most_common_diseases": [],
                "most_common_medicines": [], "status_distribution": {},
                "decisions_over_time": [],
            }

        conf_sum = sum(r.confidence for r in rows)
        time_sum = sum(r.execution_time for r in rows)
        failed = sum(1 for r in rows if r.status == DecisionStatus.FAILED.value)
        low_conf = sum(1 for r in rows if r.status == DecisionStatus.LOW_CONFIDENCE.value
                       or r.confidence < settings.MIN_CONFIDENCE)
        status_dist: dict[str, int] = {}
        disease_counts: dict[str, int] = {}
        medicine_counts: dict[str, int] = {}
        over_time: dict[str, int] = {}
        for r in rows:
            status_dist[r.status] = status_dist.get(r.status, 0) + 1
            if r.top_disease:
                disease_counts[r.top_disease] = disease_counts.get(r.top_disease, 0) + 1
            for m in (r.medicine_names or "").split(", "):
                m = m.strip()
                if m:
                    medicine_counts[m] = medicine_counts.get(m, 0) + 1
            day = r.created_at.strftime("%Y-%m-%d")
            over_time[day] = over_time.get(day, 0) + 1

        def _top(counts: dict[str, int]) -> list[dict]:
            return [{"name": k, "count": v} for k, v in
                    sorted(counts.items(), key=lambda kv: -kv[1])[:8]]

        return {
            "total_decisions": total,
            "average_confidence": round(conf_sum / total, 3),
            "average_processing_time": round(time_sum / total, 3),
            "failed_predictions": failed,
            "low_confidence_cases": low_conf,
            "most_common_diseases": _top(disease_counts),
            "most_common_medicines": _top(medicine_counts),
            "status_distribution": status_dist,
            "decisions_over_time": [{"date": d, "count": c}
                                    for d, c in sorted(over_time.items())],
        }
