"""AI Governance service — the composition root that wires everything together.

Follows SOLID + dependency injection: this service owns no persistence logic of
its own. It **composes** the focused collaborators — the decision tracker, audit
logger, model/dataset registries, version manager and the three pure engines
(explanation, confidence, pipeline) — and exposes one cohesive API to the router.
Each collaborator receives its dependencies (session factory, version manager,
``ensure_db``) explicitly, so any of them can be unit-tested or swapped in
isolation.

It also owns cross-cutting concerns that don't belong to a single collaborator:
the dashboard roll-up (which spans traces + audit logs + registries) and the
CSV / JSON / PDF export of audit logs and decision traces.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any

from backend.ai_governance import db as gov_db
from backend.ai_governance import (
    confidence_analyzer,
    explanation_engine,
    pipeline_tracker,
)
from backend.ai_governance.audit_logger import AuditLogger
from backend.ai_governance.dataset_registry import DatasetRegistry
from backend.ai_governance.decision_tracker import DecisionTracker
from backend.ai_governance.model_registry import ModelRegistry
from backend.ai_governance.schemas import (
    AuditLogItem,
    ConfidenceReport,
    DatasetEntry,
    DatasetRegisterRequest,
    DecisionPage,
    DecisionTrace,
    ExplanationReport,
    GovernanceDashboard,
    ModelEntry,
    ModelRegisterRequest,
    NameCount,
    PipelineView,
    SyncResult,
    VersionInfo,
)
from backend.ai_governance.version_manager import get_version_manager

logger = logging.getLogger("ai_governance")


class AIGovernanceService:
    """Composition root — injects and orchestrates the governance collaborators."""

    def __init__(self) -> None:
        versions = get_version_manager()
        session_factory = gov_db.Session
        self._versions = versions
        self._tracker = DecisionTracker(session_factory, gov_db.ensure_db, versions)
        self._audit = AuditLogger(session_factory)
        self._models = ModelRegistry(session_factory, versions)
        self._datasets = DatasetRegistry(session_factory, versions)

    # -- exposed collaborators (for the middleware / OCR hook) --------------
    @property
    def audit(self) -> AuditLogger:
        return self._audit

    @property
    def tracker(self) -> DecisionTracker:
        return self._tracker

    def versions(self) -> VersionInfo:
        return VersionInfo(**self._versions.as_dict())

    # -- decisions ----------------------------------------------------------
    async def search_decisions(self, **kwargs) -> DecisionPage:
        return await self._tracker.search(**kwargs)

    async def get_trace(self, trace_id: str) -> DecisionTrace | None:
        return await self._tracker.get(trace_id)

    async def explain(self, trace_id: str) -> ExplanationReport | None:
        trace = await self._tracker.get(trace_id)
        return explanation_engine.explain(trace) if trace else None

    async def confidence(self, trace_id: str) -> ConfidenceReport | None:
        trace = await self._tracker.get(trace_id)
        return confidence_analyzer.analyze(trace) if trace else None

    async def pipeline(self, trace_id: str) -> PipelineView | None:
        trace = await self._tracker.get(trace_id)
        return pipeline_tracker.build_pipeline(trace) if trace else None

    async def sync(self) -> SyncResult:
        return await self._tracker.sync_from_reports()

    # -- audit --------------------------------------------------------------
    async def search_audit_logs(self, **kwargs):
        return await self._audit.search(**kwargs)

    # -- registries ---------------------------------------------------------
    async def list_models(self) -> list[ModelEntry]:
        return await self._models.list_models()

    async def register_model(self, req: ModelRegisterRequest) -> ModelEntry:
        return await self._models.register(req)

    async def list_datasets(self) -> list[DatasetEntry]:
        return await self._datasets.list_datasets()

    async def register_dataset(self, req: DatasetRegisterRequest) -> DatasetEntry:
        return await self._datasets.register(req)

    # -- dashboard ----------------------------------------------------------
    async def dashboard(self) -> GovernanceDashboard:
        stats = await self._tracker.dashboard()
        audit_total = await self._audit.count()
        audit_failures = await self._audit.count(errors_only=True)
        models = await self._models.list_models()
        datasets = await self._datasets.list_datasets()
        return GovernanceDashboard(
            total_decisions=stats["total_decisions"],
            average_confidence=stats["average_confidence"],
            average_processing_time=stats["average_processing_time"],
            failed_predictions=stats["failed_predictions"],
            audit_failures=audit_failures,
            low_confidence_cases=stats["low_confidence_cases"],
            most_common_diseases=[NameCount(**d) for d in stats["most_common_diseases"]],
            most_common_medicines=[NameCount(**m) for m in stats["most_common_medicines"]],
            status_distribution=stats["status_distribution"],
            decisions_over_time=stats["decisions_over_time"],
            total_audit_logs=audit_total,
            models_registered=len(models),
            datasets_registered=len(datasets),
            versions=self.versions(),
            generated_at=datetime.utcnow(),
        )

    # -- export (Requirement: EXPORT) ---------------------------------------
    async def export_audit_logs(self, fmt: str) -> tuple[bytes, str, str]:
        rows = await self._audit.all_for_export()
        return self._export(
            [r.model_dump(mode="json") for r in rows], fmt,
            base_name="audit_logs",
            columns=["id", "created_at", "user", "method", "api", "status_code",
                     "processing_time_ms", "model_used", "error"],
            title="AI Governance — Audit Logs",
        )

    async def export_decisions(self, fmt: str) -> tuple[bytes, str, str]:
        rows = await self._tracker.all_traces()
        data = [r.item() for r in rows]
        # item() returns datetimes — normalise for serialisation.
        for d in data:
            if isinstance(d.get("created_at"), datetime):
                d["created_at"] = d["created_at"].isoformat()
        return self._export(
            data, fmt, base_name="decision_traces",
            columns=["trace_id", "created_at", "patient_name", "top_disease",
                     "medicine_count", "confidence", "status", "execution_time",
                     "model_version", "dataset_version"],
            title="AI Governance — Decision Traces",
        )

    # -- export helpers -----------------------------------------------------
    def _export(self, rows: list[dict[str, Any]], fmt: str, *, base_name: str,
                columns: list[str], title: str) -> tuple[bytes, str, str]:
        fmt = (fmt or "json").lower()
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        if fmt == "json":
            payload = json.dumps({"title": title, "exported_at": stamp, "rows": rows},
                                 indent=2, default=str).encode("utf-8")
            return payload, "application/json", f"{base_name}-{stamp}.json"
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow({c: r.get(c, "") for c in columns})
            return buf.getvalue().encode("utf-8"), "text/csv", f"{base_name}-{stamp}.csv"
        if fmt == "pdf":
            return self._export_pdf(rows, columns, title), "application/pdf", f"{base_name}-{stamp}.pdf"
        raise ValueError(f"Unsupported export format '{fmt}'. Use csv, json or pdf.")

    def _export_pdf(self, rows: list[dict[str, Any]], columns: list[str], title: str) -> bytes:
        """Render an audit/decision export as a PDF (reportlab, lazy-imported)."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "PDF export requires the 'reportlab' package (pip install reportlab). "
                "CSV and JSON export are available without it."
            ) from exc

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=12 * mm, rightMargin=12 * mm,
                                topMargin=12 * mm, bottomMargin=12 * mm)
        styles = getSampleStyleSheet()
        story = [Paragraph(title, styles["Title"]),
                 Paragraph(f"Exported {datetime.utcnow():%Y-%m-%d %H:%M UTC} · "
                           f"{len(rows)} record(s)", styles["Normal"]),
                 Spacer(1, 6 * mm)]

        def _cell(v: Any) -> str:
            s = "" if v is None else str(v)
            return (s[:40] + "…") if len(s) > 40 else s

        header = [c.replace("_", " ").title() for c in columns]
        data = [header] + [[_cell(r.get(c, "")) for c in columns] for r in rows[:400]]
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(table)
        doc.build(story)
        return buf.getvalue()


_SERVICE: AIGovernanceService | None = None


def get_service() -> AIGovernanceService:
    """Process-wide singleton composition root."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AIGovernanceService()
    return _SERVICE
