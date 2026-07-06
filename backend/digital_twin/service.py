"""Digital Twin service — aggregate every prior analysis into one live profile.

The twin is **derived, not duplicated**: it reads the existing Medical-Report
store (which auto-captures each OCR analysis together with its medicines, disease
prediction, drug interactions and clinical decision) and folds a patient's
reports — oldest→newest — into a single evolving profile via the pure engines
(health score, trends, risk, prediction, timeline). RAG enriches the
recommendations with evidence. A snapshot is persisted per patient so analytics
and the twin's evolution are durable.

Design contract (identical to the other modules):

* **Async everywhere**; the read of the reports DB and the twin store are async.
* **Best-effort enrichment** — a RAG failure degrades gracefully, never raising.
* **Best-effort persistence** — snapshot upserts never break a twin computation.
* **Non-invasive** — reads the reports DB read-only; changes nothing existing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.digital_twin import health_score, prediction_engine, risk_engine, timeline_engine
from backend.digital_twin import trend_engine as te
from backend.digital_twin.models import Base, TwinSnapshot, utcnow
from backend.digital_twin.schemas import (
    ClinicalDecisionItem,
    DigitalTwin,
    DigitalTwinAnalytics,
    DiseaseHistoryItem,
    EvidenceItem,
    HealthScoreBreakdown,
    InteractionSummary,
    MedicineHistoryItem,
    PatientListItem,
    Prediction,
    ReportRef,
    RiskAssessment,
    RiskLevel,
    TrendDirection,
)
from backend.report_generator.models import ReportRecord  # read-only reuse of the model

logger = logging.getLogger("digital_twin")

_RISK_SEVERITY = {"none": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}


def slugify(name: str | None) -> str:
    """Stable patient id from a display name ('John Doe' → 'john-doe')."""
    s = (name or "").strip().lower()
    if not s:
        return "unknown"
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"


def _norm_med(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


# ==========================================================================
# Persistence — the twin snapshot store (own DB), + a read-only reports engine.
# ==========================================================================
_engine = create_async_engine(settings.DIGITAL_TWIN_DB_URL, echo=False, pool_pre_ping=True, future=True)
_Session: async_sessionmaker[AsyncSession] = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

_reports_engine = create_async_engine(settings.REPORTS_DB_URL, echo=False, pool_pre_ping=True, future=True)
_ReportsSession: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _reports_engine, expire_on_commit=False, class_=AsyncSession
)

_db_lock = asyncio.Lock()
_db_ready = False


async def _ensure_db() -> None:
    global _db_ready
    if _db_ready:
        return
    async with _db_lock:
        if _db_ready:
            return
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_ready = True
        logger.info("Digital-twin snapshot store ready (%s)", settings.DIGITAL_TWIN_DB_URL.split("://")[0])


# ==========================================================================
# Encounter extraction (report content → the compact shape engines consume)
# ==========================================================================
def _to_encounter(row: ReportRecord) -> dict:
    content = row.content or {}
    clinical = content.get("clinical") or {}
    interactions = content.get("drug_interactions") or {}
    meds = content.get("medicines") or []
    disease_pred = content.get("disease_prediction") or []

    medicine_entries = []
    med_names: list[str] = []
    for m in meds:
        name = m.get("name") or m.get("raw_text")
        if not name:
            continue
        norm = _norm_med(name)
        med_names.append(norm)
        medicine_entries.append({
            "name": name, "norm": norm,
            "dosage": m.get("dosage"), "confidence": m.get("confidence"),
        })

    # Disease signal comes from the clinical disease-prediction list, the report's
    # denormalised top_disease, and (as a fallback) the parsed diagnosis field.
    diagnosis = (content.get("patient") or {}).get("diagnosis")
    top_disease = row.top_disease or (disease_pred[0].get("disease") if disease_pred else None) or diagnosis
    diseases = [d.get("disease") for d in disease_pred if d.get("disease")]
    if diagnosis and diagnosis not in diseases:
        diseases.append(diagnosis)
    if top_disease and top_disease not in diseases:
        diseases.insert(0, top_disease)

    return {
        "id": row.id,
        "created_at": row.created_at,
        "medicines": medicine_entries,
        "medicine_names": med_names,
        "top_disease": top_disease,
        "diseases": diseases,
        "overall_confidence": float(content.get("overall_confidence") or row.overall_confidence or 0.0),
        "risk_level": (clinical.get("risk_level") or row.risk_level or "").lower() or None,
        "risk_score": clinical.get("risk_score"),
        "interaction_risk": (interactions.get("overall_risk") or "none"),
        "interaction_count": len(interactions.get("interactions") or []),
        "interactions": interactions.get("interactions") or [],
        "warnings": content.get("warnings") or [],
        "red_flags": clinical.get("red_flags") or [],
        "recommendations": content.get("recommendations") or clinical.get("recommended_next_steps") or [],
        "follow_up": content.get("follow_up") or clinical.get("follow_up") or [],
        "contraindications": content.get("contraindications") or clinical.get("contraindications") or [],
        "clinical_summary": clinical.get("clinical_summary") or "",
    }


# ==========================================================================
# Service
# ==========================================================================
class DigitalTwinService:
    """Builds, persists and serves patient Digital Twins."""

    # -- reads from the reports store -------------------------------------
    async def _patient_report_rows(self, patient_id: str) -> tuple[str, list[ReportRecord]]:
        """Return (display_name, chronological report rows) for a patient id."""
        async with _ReportsSession() as session:
            # Resolve the display name from the id by scanning distinct names.
            names = (await session.execute(
                select(ReportRecord.patient_name).distinct()
            )).scalars().all()
            display = next((n for n in names if slugify(n) == patient_id), None)

            stmt = select(ReportRecord)
            if patient_id == "unknown" and display is None:
                stmt = stmt.where(or_(ReportRecord.patient_name.is_(None), ReportRecord.patient_name == ""))
                display = "Unknown patient"
            else:
                stmt = stmt.where(ReportRecord.patient_name == display)
            stmt = stmt.order_by(ReportRecord.created_at.asc())
            rows = (await session.execute(stmt)).scalars().all()
        return (display or "Unknown patient"), list(rows)

    async def list_patients(self) -> list[PatientListItem]:
        """Every patient that has at least one report, newest activity first."""
        async with _ReportsSession() as session:
            stmt = (
                select(
                    ReportRecord.patient_name,
                    func.count(ReportRecord.id),
                    func.max(ReportRecord.created_at),
                )
                .group_by(ReportRecord.patient_name)
                .order_by(func.max(ReportRecord.created_at).desc())
            )
            rows = (await session.execute(stmt)).all()

        # Enrich with any persisted snapshot headline metrics.
        await _ensure_db()
        async with _Session() as session:
            snaps = {s.patient_id: s for s in (await session.execute(select(TwinSnapshot))).scalars().all()}

        items: list[PatientListItem] = []
        for name, count, last_seen in rows:
            pid = slugify(name)
            snap = snaps.get(pid)
            items.append(PatientListItem(
                patient_id=pid,
                patient_name=name or "Unknown patient",
                report_count=int(count),
                last_seen=last_seen,
                health_score=snap.health_score if snap else None,
                risk_level=RiskLevel(snap.risk_level) if snap and snap.risk_level in RiskLevel._value2member_map_ else None,
            ))
        return items

    # -- RAG enrichment (best-effort) -------------------------------------
    async def _rag_evidence(self, top_disease: str | None, medicines: list[str]) -> tuple[str | None, list[str], list[EvidenceItem]]:
        if not settings.DIGITAL_TWIN_USE_RAG:
            return None, [], []
        try:
            from backend.rag.rag_service import get_rag_service

            topic = top_disease or "the patient's medications"
            meds = ", ".join(medicines[:6])
            query = (f"Management guidelines, monitoring and follow-up for {topic}"
                     + (f" with medicines {meds}" if meds else ""))[:400]
            info = await get_rag_service().aquery(query)
            if not isinstance(info, dict) or info.get("provider") == "unavailable":
                return None, [], []
            evidence = [
                EvidenceItem(source=c.get("source", "knowledge-base"), text=(c.get("text", "") or "")[:400])
                for c in (info.get("chunks", []) or [])[:4]
            ]
            return info.get("answer"), info.get("sources", []) or [], evidence
        except Exception as exc:  # noqa: BLE001 — RAG is optional
            logger.debug("Digital-twin RAG enrichment skipped: %s", exc)
            return None, [], []

    # -- aggregation helpers ----------------------------------------------
    @staticmethod
    def _medicine_history(encounters: list[dict]) -> list[MedicineHistoryItem]:
        latest_meds = set(encounters[-1]["medicine_names"]) if encounters else set()
        agg: dict[str, dict] = {}
        for enc in encounters:
            for m in enc["medicines"]:
                norm = m["norm"]
                rec = agg.setdefault(norm, {"name": m["name"], "occurrences": 0,
                                            "first_seen": enc["created_at"], "last_seen": enc["created_at"],
                                            "last_dosage": m.get("dosage")})
                rec["occurrences"] += 1
                rec["last_seen"] = enc["created_at"]
                rec["name"] = m["name"]
                if m.get("dosage"):
                    rec["last_dosage"] = m["dosage"]
        out = [
            MedicineHistoryItem(
                name=r["name"].title(), occurrences=r["occurrences"],
                first_seen=r["first_seen"], last_seen=r["last_seen"],
                last_dosage=r["last_dosage"],
                status="active" if norm in latest_meds else "past",
            )
            for norm, r in agg.items()
        ]
        out.sort(key=lambda x: (x.status != "active", -x.occurrences))
        return out

    @staticmethod
    def _disease_history(encounters: list[dict]) -> list[DiseaseHistoryItem]:
        agg: dict[str, dict] = {}
        for enc in encounters:
            for d in enc["diseases"]:
                rec = agg.setdefault(d, {"occurrences": 0, "first_seen": enc["created_at"], "last_seen": enc["created_at"]})
                rec["occurrences"] += 1
                rec["last_seen"] = enc["created_at"]
        out = [DiseaseHistoryItem(disease=d, occurrences=r["occurrences"],
                                  first_seen=r["first_seen"], last_seen=r["last_seen"])
               for d, r in agg.items()]
        out.sort(key=lambda x: -x.occurrences)
        return out

    def _build_trends(self, encounters: list[dict], health: dict) -> dict:
        """Assemble the five tracked trends for the charts."""
        # Health score trend (from the health engine's per-encounter series).
        health_points = [(t, v) for t, v in health["series"]]
        # OCR confidence trend.
        ocr_points = [(e["created_at"], float(e["overall_confidence"]) * 100.0) for e in encounters]
        # Disease burden trend (clinical risk score; 0 when absent).
        disease_points = [(e["created_at"], float(e.get("risk_score") or _RISK_SEVERITY.get(e.get("risk_level") or "none", 0) * 25)) for e in encounters]
        # Risk trend (categorical severity → 0..100).
        risk_points = [(e["created_at"], _RISK_SEVERITY.get((e.get("risk_level") or "none"), 0) * 25.0) for e in encounters]
        # Medicine adherence trend (the adherence factor per encounter).
        adherence_points = []
        for i, e in enumerate(encounters):
            factors = health_score.factor_scores(e, encounters[i - 1] if i > 0 else None)
            adherence_points.append((e["created_at"], factors["adherence"]))

        return {
            "health_score": te.build_trend("health_score", health_points, higher_is_better=True, eps=4),
            "ocr_quality": te.build_trend("ocr_quality", ocr_points, higher_is_better=True, eps=5),
            "disease": te.build_trend("disease", disease_points, higher_is_better=False, eps=8),
            "risk": te.build_trend("risk", risk_points, higher_is_better=False, eps=12),
            "medicine": te.build_trend("medicine", adherence_points, higher_is_better=True, eps=6),
        }

    @staticmethod
    def _interaction_summary(encounters: list[dict]) -> InteractionSummary:
        total = sum(e["interaction_count"] for e in encounters)
        highest = "none"
        for e in encounters:
            r = (e.get("interaction_risk") or "none")
            if _RISK_SEVERITY.get(r, 0) > _RISK_SEVERITY.get(highest, 0):
                highest = r
        recent: list[dict] = []
        for e in reversed(encounters):
            for it in e.get("interactions", [])[:3]:
                recent.append({
                    "medicines": it.get("medicines", []),
                    "severity": it.get("severity"),
                    "risk": it.get("clinical_risk") or it.get("risk"),
                })
            if recent:
                break
        return InteractionSummary(total_flagged=total, highest_risk=highest, recent=recent[:4])

    def _build_recommendations(self, encounters: list[dict], risk: RiskAssessment,
                               trends: dict, rag_answer: str | None) -> list[str]:
        recs: list[str] = []
        latest = encounters[-1]
        for r in (latest.get("recommendations") or [])[:4]:
            recs.append(r)
        for f in (latest.get("follow_up") or [])[:3]:
            recs.append(f if isinstance(f, str) else str(f))

        if risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            recs.append("Predicted risk is elevated — arrange a clinical review and reconcile all medicines.")
        if trends["health_score"].direction == TrendDirection.WORSENING:
            recs.append("Health score is trending down — investigate the contributing factors at the next visit.")
        if trends["ocr_quality"].direction == TrendDirection.WORSENING:
            recs.append("Recent prescription scans are lower quality — recapture images for more reliable analysis.")
        if rag_answer:
            recs.append("Evidence-based guidance: " + rag_answer.strip().split("\n")[0][:240])

        # De-duplicate, preserve order.
        seen: set[str] = set()
        out: list[str] = []
        for r in recs:
            key = r.strip().lower()
            if r.strip() and key not in seen:
                seen.add(key)
                out.append(r.strip())
        return out[:8]

    @staticmethod
    def _ai_summary(name: str, score: float, status: TrendDirection, risk: RiskAssessment,
                    encounters: list[dict], med_count: int, top_disease: str | None) -> str:
        parts = [
            f"{name} has {len(encounters)} recorded analysis/analyses.",
            f"Current health score is {score:.0f}/100 and is {status.value}.",
            f"Predicted future risk is {risk.level.value}.",
        ]
        if top_disease:
            parts.append(f"The most frequent condition on record is {top_disease}.")
        if med_count:
            parts.append(f"{med_count} distinct medicine(s) appear across the history.")
        return " ".join(parts)

    # -- main build --------------------------------------------------------
    async def build_twin(self, patient_id: str, *, persist: bool = True) -> DigitalTwin:
        """Compute (and optionally persist) the Digital Twin for a patient."""
        name, rows = await self._patient_report_rows(patient_id)
        encounters = [_to_encounter(r) for r in rows]

        if not encounters:
            return DigitalTwin(patient_id=patient_id, patient_name=name, generated_at=utcnow(),
                               ai_summary="No analyses on record for this patient yet.")

        # Engines.
        health = health_score.compute(encounters)
        trends = self._build_trends(encounters, health)
        health_status = trends["health_score"].direction
        risk = risk_engine.assess(encounters, health_status)
        prediction = prediction_engine.forecast([v for _, v in health["series"]])
        timeline = timeline_engine.build(encounters)

        # Aggregations.
        medicines = self._medicine_history(encounters)
        diseases = self._disease_history(encounters)
        interactions = self._interaction_summary(encounters)
        clinical_decisions = [
            ClinicalDecisionItem(
                timestamp=e["created_at"], risk_level=e.get("risk_level"),
                summary=e.get("clinical_summary") or "", red_flag_count=len(e.get("red_flags") or []),
                report_id=e["id"],
            )
            for e in reversed(encounters) if e.get("risk_level") or e.get("clinical_summary")
        ]
        reports = [
            ReportRef(id=e["id"], created_at=e["created_at"], top_disease=e.get("top_disease"),
                      risk_level=e.get("risk_level"), medicine_count=len(e["medicine_names"]),
                      confidence=float(e["overall_confidence"]))
            for e in reversed(encounters)
        ]

        # RAG evidence.
        latest = encounters[-1]
        active_meds = [m.name for m in medicines if m.status == "active"]
        rag_answer, rag_sources, evidence = await self._rag_evidence(latest.get("top_disease"), active_meds)

        top_disease = diseases[0].disease if diseases else None
        recommendations = self._build_recommendations(encounters, risk, trends, rag_answer)
        breakdown = HealthScoreBreakdown(**health["breakdown"])

        twin = DigitalTwin(
            patient_id=patient_id, patient_name=name, generated_at=utcnow(),
            report_count=len(encounters),
            first_seen=encounters[0]["created_at"], last_seen=encounters[-1]["created_at"],
            health_score=health["score"], health_status=health_status,
            health_score_breakdown=breakdown, risk=risk, prediction=prediction,
            trends=trends, timeline=timeline, medicines=medicines, diseases=diseases,
            clinical_decisions=clinical_decisions, interactions=interactions, reports=reports,
            ai_summary=self._ai_summary(name, health["score"], health_status, risk, encounters, len(medicines), top_disease),
            recommendations=recommendations, rag_sources=rag_sources, evidence=evidence,
            data_sources={
                "reports": len(encounters),
                "medicines": len(medicines),
                "diseases": len(diseases),
                "interactions_flagged": interactions.total_flagged,
                "clinical_decisions": len(clinical_decisions),
                "rag_documents": len(evidence),
            },
        )

        if persist:
            await self._save(twin, top_disease)
        return twin

    async def _save(self, twin: DigitalTwin, top_disease: str | None) -> None:
        """Upsert the twin snapshot. Best-effort: never raises."""
        try:
            await _ensure_db()
            async with _Session() as session:
                row = await session.get(TwinSnapshot, twin.patient_id)
                if row is None:
                    row = TwinSnapshot(patient_id=twin.patient_id)
                    session.add(row)
                row.patient_name = twin.patient_name
                row.computed_at = twin.generated_at or utcnow()
                row.health_score = twin.health_score
                row.health_status = twin.health_status.value
                row.risk_level = twin.risk.level.value
                row.report_count = twin.report_count
                row.top_disease = top_disease
                row.snapshot = twin.model_dump(mode="json")
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save digital-twin snapshot for %s", twin.patient_id)

    # -- recalculation + analytics ----------------------------------------
    async def recalculate(self, patient_id: str | None) -> dict:
        """Recompute one patient (or everyone) and upsert snapshots."""
        started = time.perf_counter()
        if patient_id:
            ids = [patient_id]
        else:
            ids = [p.patient_id for p in await self.list_patients()]
        done: list[str] = []
        for pid in ids:
            try:
                await self.build_twin(pid, persist=True)
                done.append(pid)
            except Exception:  # noqa: BLE001 — one bad patient never stops the batch
                logger.exception("Recalculation failed for patient %s", pid)
        return {"recalculated": len(done), "patients": done,
                "took_ms": round((time.perf_counter() - started) * 1000, 1)}

    async def analytics(self) -> DigitalTwinAnalytics:
        """Population-level analytics across all persisted twin snapshots."""
        await _ensure_db()
        async with _Session() as session:
            snaps = (await session.execute(select(TwinSnapshot))).scalars().all()
        if not snaps:
            return DigitalTwinAnalytics(recomputed_at=utcnow())

        risk_dist: dict[str, int] = {}
        status_dist: dict[str, int] = {}
        disease_counts: dict[str, int] = {}
        total_score = 0.0
        at_risk = 0
        for s in snaps:
            risk_dist[s.risk_level] = risk_dist.get(s.risk_level, 0) + 1
            status_dist[s.health_status] = status_dist.get(s.health_status, 0) + 1
            total_score += s.health_score
            if s.risk_level in ("high", "critical"):
                at_risk += 1
            if s.top_disease:
                disease_counts[s.top_disease] = disease_counts.get(s.top_disease, 0) + 1

        top_diseases = sorted(
            ({"disease": d, "count": c} for d, c in disease_counts.items()),
            key=lambda x: -x["count"],
        )[:5]
        return DigitalTwinAnalytics(
            total_patients=len(snaps),
            average_health_score=round(total_score / len(snaps), 1),
            patients_at_risk=at_risk,
            risk_distribution=risk_dist,
            status_distribution=status_dist,
            top_diseases=top_diseases,
            recomputed_at=utcnow(),
        )


_SERVICE: DigitalTwinService | None = None


def get_service() -> DigitalTwinService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = DigitalTwinService()
    return _SERVICE
