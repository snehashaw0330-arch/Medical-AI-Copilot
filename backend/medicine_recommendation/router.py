"""FastAPI routes for the Medicine Recommendation module (all async).

Endpoints (Requirement 5)
-------------------------
* ``POST   /medicine/recommend``              — build a recommendation report
* ``GET    /medicine/recommendations``        — paginated list of past reports
* ``GET    /medicine/recommendations/{id}``   — full stored report
* ``DELETE /medicine/recommendations``        — clear stored reports

The router never lets a failure crash the app: problems surface as actionable
4xx/5xx responses with clear messages. The static ``/recommendations`` route is
declared before the dynamic ``/recommendations/{record_id}`` route so it is
matched first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.medicine_recommendation.schemas import (
    MedicineRecommendRequest,
    RecommendationHistoryPage,
    RecommendationReport,
)
from backend.medicine_recommendation.service import get_service

logger = logging.getLogger("medicine_recommendation")

router = APIRouter(prefix="/medicine", tags=["medicine-recommendation"])


@router.post("/recommend", response_model=RecommendationReport)
async def recommend(req: MedicineRecommendRequest) -> RecommendationReport:
    """Build a medicine-recommendation report (alternatives + drug info + RAG)."""
    try:
        return await get_service().recommend(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Medicine recommendation failed")
        raise HTTPException(
            status_code=500, detail=f"Medicine recommendation failed: {exc}"
        ) from exc


@router.get("/recommendations", response_model=RecommendationHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> RecommendationHistoryPage:
    """Paginated list of past recommendation reports (newest first)."""
    try:
        result = await get_service().list_history(page=page, page_size=page_size)
        return RecommendationHistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list recommendation history")
        raise HTTPException(
            status_code=500, detail=f"Could not load history: {exc}"
        ) from exc


@router.delete("/recommendations")
async def clear_history() -> dict:
    """Delete every stored recommendation report."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear recommendation history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/recommendations/{record_id}", response_model=RecommendationReport)
async def get_report(record_id: str) -> RecommendationReport:
    """Full stored report for a single past recommendation."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"No recommendation record: {record_id}"
        )
    return RecommendationReport(**report)
