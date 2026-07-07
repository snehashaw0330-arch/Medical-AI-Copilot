"""FastAPI routes for the AI Governance, Audit & Explainability module (async).

Surface (all under ``/governance``):

* ``GET  /governance/dashboard``                       — governance KPIs
* ``GET  /governance/versions``                        — pinned component versions
* ``POST /governance/sync``                            — backfill traces from reports
* ``GET  /governance/decisions``                       — search AI decision traces
* ``GET  /governance/decisions/export``                — export traces (csv/json/pdf)
* ``GET  /governance/decisions/{trace_id}``            — full decision trace
* ``GET  /governance/decisions/{trace_id}/explanation``— explainability report
* ``GET  /governance/decisions/{trace_id}/confidence`` — confidence analysis
* ``GET  /governance/decisions/{trace_id}/pipeline``   — pipeline view
* ``GET  /governance/audit-logs``                      — search audit logs
* ``GET  /governance/audit-logs/export``               — export audit logs
* ``GET  /governance/models`` / ``POST /governance/models``     — model registry
* ``GET  /governance/datasets`` / ``POST /governance/datasets`` — dataset registry

Static sub-paths precede the dynamic ``/decisions/{trace_id}`` route so they are
matched first. Failures surface as actionable HTTP errors; internal
enrichment/persistence degrades gracefully inside the service.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.ai_governance.schemas import (
    AuditLogPage,
    ConfidenceReport,
    DatasetEntry,
    DatasetRegisterRequest,
    DecisionPage,
    DecisionTrace,
    ExplanationReport,
    GovernanceDashboard,
    ModelEntry,
    ModelRegisterRequest,
    PipelineView,
    SyncResult,
    VersionInfo,
)
from backend.ai_governance.service import get_service

logger = logging.getLogger("ai_governance")

router = APIRouter(prefix="/governance", tags=["ai-governance"])


# ==========================================================================
# Dashboard / versions / maintenance
# ==========================================================================
@router.get("/dashboard", response_model=GovernanceDashboard)
async def dashboard() -> GovernanceDashboard:
    """Governance KPIs across decisions, audit logs and registries."""
    try:
        return await get_service().dashboard()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to build governance dashboard")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/versions", response_model=VersionInfo)
async def versions() -> VersionInfo:
    """The pinned model / dataset / prompt / pipeline / RAG-index versions."""
    return get_service().versions()


@router.post("/sync", response_model=SyncResult)
async def sync() -> SyncResult:
    """Backfill decision traces from the existing medical-report store."""
    try:
        return await get_service().sync()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Governance sync failed")
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}") from exc


# ==========================================================================
# Decisions — search + export (static) before dynamic /{trace_id}
# ==========================================================================
@router.get("/decisions", response_model=DecisionPage)
async def search_decisions(
    patient: str | None = Query(default=None),
    medicine: str | None = Query(default=None),
    disease: str | None = Query(default=None),
    prediction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    model_version: str | None = Query(default=None),
    dataset_version: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> DecisionPage:
    """Search AI decision traces (patient / medicine / disease / version / date)."""
    try:
        return await get_service().search_decisions(
            patient=patient, medicine=medicine, disease=disease, prediction=prediction,
            status=status, model_version=model_version, dataset_version=dataset_version,
            min_confidence=min_confidence, date_from=date_from, date_to=date_to,
            page=page, page_size=page_size,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Decision search failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/decisions/export")
async def export_decisions(fmt: str = Query(default="csv", pattern="^(csv|json|pdf)$")) -> Response:
    """Export decision traces as CSV, JSON or PDF."""
    return await _export(get_service().export_decisions, fmt)


@router.get("/decisions/{trace_id}", response_model=DecisionTrace)
async def get_trace(trace_id: str) -> DecisionTrace:
    """The full, reproducible decision trace for one AI decision."""
    trace = await get_service().get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Unknown trace: {trace_id}")
    return trace


@router.get("/decisions/{trace_id}/explanation", response_model=ExplanationReport)
async def explanation(trace_id: str) -> ExplanationReport:
    """The full explainability report for one decision trace."""
    report = await get_service().explain(trace_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Unknown trace: {trace_id}")
    return report


@router.get("/decisions/{trace_id}/confidence", response_model=ConfidenceReport)
async def confidence(trace_id: str) -> ConfidenceReport:
    """The confidence / reliability / calibration analysis for one trace."""
    report = await get_service().confidence(trace_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Unknown trace: {trace_id}")
    return report


@router.get("/decisions/{trace_id}/pipeline", response_model=PipelineView)
async def pipeline(trace_id: str) -> PipelineView:
    """The per-step pipeline view (time / status / confidence / warnings)."""
    view = await get_service().pipeline(trace_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"Unknown trace: {trace_id}")
    return view


# ==========================================================================
# Audit logs
# ==========================================================================
@router.get("/audit-logs", response_model=AuditLogPage)
async def audit_logs(
    user: str | None = Query(default=None),
    api: str | None = Query(default=None),
    method: str | None = Query(default=None),
    status_code: int | None = Query(default=None),
    errors_only: bool = Query(default=False),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> AuditLogPage:
    """Search the immutable API audit log."""
    try:
        return await get_service().search_audit_logs(
            user=user, api=api, method=method, status_code=status_code,
            errors_only=errors_only, date_from=date_from, date_to=date_to,
            page=page, page_size=page_size,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Audit-log search failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/audit-logs/export")
async def export_audit_logs(fmt: str = Query(default="csv", pattern="^(csv|json|pdf)$")) -> Response:
    """Export audit logs as CSV, JSON or PDF."""
    return await _export(get_service().export_audit_logs, fmt)


# ==========================================================================
# Registries
# ==========================================================================
@router.get("/models", response_model=list[ModelEntry])
async def list_models() -> list[ModelEntry]:
    """Every registered AI model (seeded with the shipped models on first read)."""
    try:
        return await get_service().list_models()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list models")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/models", response_model=ModelEntry)
async def register_model(req: ModelRegisterRequest) -> ModelEntry:
    """Register a new model version or update an existing one."""
    try:
        return await get_service().register_model(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to register model")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/datasets", response_model=list[DatasetEntry])
async def list_datasets() -> list[DatasetEntry]:
    """Every registered dataset (seeded with the shipped datasets on first read)."""
    try:
        return await get_service().list_datasets()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list datasets")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/datasets", response_model=DatasetEntry)
async def register_dataset(req: DatasetRegisterRequest) -> DatasetEntry:
    """Register a new dataset version or update an existing one."""
    try:
        return await get_service().register_dataset(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to register dataset")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ==========================================================================
# Shared export helper
# ==========================================================================
async def _export(export_fn, fmt: str) -> Response:
    try:
        payload, media_type, filename = await export_fn(fmt)
    except RuntimeError as exc:  # reportlab missing for PDF
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Export failed")
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
    return Response(
        content=payload, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
