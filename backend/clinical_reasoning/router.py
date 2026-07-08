"""FastAPI routes for the Clinical Reasoning Platform (all async).

Endpoints
---------
* ``POST   /reasoning/analyze``     — run the full step-by-step reasoning pipeline
* ``GET    /reasoning/pipeline``    — the static pipeline definition (for the UI)
* ``GET    /reasoning/history``     — paginated list of past reasoning reports
* ``GET    /reasoning/stats``       — dashboard aggregates (incl. cache stats)
* ``GET    /reasoning/{id}``        — full stored report for one run
* ``DELETE /reasoning/history``     — clear stored reports

Every route wraps the service so a failure surfaces as an actionable HTTP error
rather than crashing the app. Static sub-paths are declared before the dynamic
``/{record_id}`` route so they match first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.clinical_reasoning.reasoning_engine import _PIPELINE
from backend.clinical_reasoning.schemas import (
    ClinicalReasoningReport,
    ReasoningHistoryPage,
    ReasoningRequest,
    ReasoningStats,
)
from backend.clinical_reasoning.service import get_service

logger = logging.getLogger("clinical_reasoning")

router = APIRouter(prefix="/reasoning", tags=["clinical-reasoning"])


@router.post("/analyze", response_model=ClinicalReasoningReport)
async def analyze(req: ReasoningRequest) -> ClinicalReasoningReport:
    """Run the full step-by-step clinical reasoning pipeline for the inputs."""
    try:
        return await get_service().analyze(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Clinical reasoning failed")
        raise HTTPException(
            status_code=500, detail=f"Clinical reasoning failed: {exc}"
        ) from exc


@router.get("/pipeline")
async def pipeline() -> dict:
    """Return the static pipeline definition so the UI can render it before a run."""
    return {
        "steps": [
            {"order": i + 1, "key": key, "name": name}
            for i, (key, name) in enumerate(_PIPELINE)
        ]
    }


@router.get("/history", response_model=ReasoningHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ReasoningHistoryPage:
    """Paginated list of past reasoning reports (newest first)."""
    try:
        result = await get_service().list_history(page=page, page_size=page_size)
        return ReasoningHistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list reasoning history")
        raise HTTPException(
            status_code=500, detail=f"Could not load history: {exc}"
        ) from exc


@router.get("/stats", response_model=ReasoningStats)
async def stats() -> ReasoningStats:
    """Aggregate stats for the dashboard cards, including cache metrics."""
    try:
        return ReasoningStats(**await get_service().compute_stats())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute reasoning stats")
        raise HTTPException(
            status_code=500, detail=f"Could not load stats: {exc}"
        ) from exc


@router.delete("/history")
async def clear_history() -> dict:
    """Delete every stored reasoning report."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear reasoning history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=ClinicalReasoningReport)
async def get_report(record_id: str) -> ClinicalReasoningReport:
    """Full stored report for a single past reasoning run."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"No reasoning record: {record_id}"
        )
    return ClinicalReasoningReport(**report)
