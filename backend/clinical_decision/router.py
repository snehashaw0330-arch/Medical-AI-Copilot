"""FastAPI routes for the Clinical Decision Support module (all async).

Endpoints
---------
* ``POST   /clinical/analyze``      — run a full clinical analysis
* ``GET    /clinical/history``      — paginated list of past analyses
* ``GET    /clinical/stats``        — dashboard risk-level aggregates
* ``GET    /clinical/{id}``         — full stored report for one analysis
* ``DELETE /clinical/history``      — clear stored analyses

The router never lets an analysis failure crash the app: problems surface as
actionable 4xx/5xx responses with clear messages. Static sub-paths (``/history``,
``/stats``) are declared before the dynamic ``/{record_id}`` route so they are
matched first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.clinical_decision.schemas import (
    ClinicalAnalysisRequest,
    ClinicalHistoryPage,
    ClinicalReport,
    ClinicalStats,
)
from backend.clinical_decision.service import get_service

logger = logging.getLogger("clinical_decision")

router = APIRouter(prefix="/clinical", tags=["clinical-decision"])


@router.post("/analyze", response_model=ClinicalReport)
async def analyze(req: ClinicalAnalysisRequest) -> ClinicalReport:
    """Run a full clinical decision-support analysis for the supplied inputs."""
    try:
        return await get_service().analyze(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Clinical analysis failed")
        raise HTTPException(
            status_code=500, detail=f"Clinical analysis failed: {exc}"
        ) from exc


@router.get("/history", response_model=ClinicalHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ClinicalHistoryPage:
    """Paginated list of past clinical analyses (newest first)."""
    try:
        result = await get_service().list_history(page=page, page_size=page_size)
        return ClinicalHistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list clinical history")
        raise HTTPException(
            status_code=500, detail=f"Could not load history: {exc}"
        ) from exc


@router.get("/stats", response_model=ClinicalStats)
async def stats() -> ClinicalStats:
    """Aggregate risk-level counts for the dashboard cards."""
    try:
        return ClinicalStats(**await get_service().compute_stats())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute clinical stats")
        raise HTTPException(
            status_code=500, detail=f"Could not load stats: {exc}"
        ) from exc


@router.delete("/history")
async def clear_history() -> dict:
    """Delete every stored clinical analysis."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear clinical history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=ClinicalReport)
async def get_report(record_id: str) -> ClinicalReport:
    """Full stored report for a single past analysis."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"No clinical record: {record_id}"
        )
    return ClinicalReport(**report)
