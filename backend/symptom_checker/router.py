"""FastAPI routes for the Symptom Checker & Triage module (all async).

Endpoints
---------
* ``POST   /symptoms/analyze``   — run a full symptom-checker & triage assessment
* ``GET    /symptoms/catalog``   — categorized symptom list + duration options
* ``GET    /symptoms/suggest``   — autocomplete for the symptom search box
* ``GET    /symptoms/history``   — paginated list of past assessments
* ``DELETE /symptoms/history``   — clear stored assessments
* ``GET    /symptoms/{id}``      — full stored report for one assessment

The required endpoints (Requirement 7) are ``/analyze``, ``/history`` and
``/{id}``; ``/catalog`` and ``/suggest`` support the frontend picker/search
(Requirement 8). The router never lets an analysis failure crash the app:
problems surface as actionable 4xx/5xx responses. Static sub-paths are declared
before the dynamic ``/{record_id}`` route so they are matched first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.symptom_checker.schemas import (
    SymptomAnalysisRequest,
    SymptomCatalog,
    TriageAssessment,
    TriageHistoryPage,
)
from backend.symptom_checker.service import get_service
from backend.symptom_checker.symptom_matcher import get_matcher

logger = logging.getLogger("symptom_checker")

router = APIRouter(prefix="/symptoms", tags=["symptom-checker"])


@router.post("/analyze", response_model=TriageAssessment)
async def analyze(req: SymptomAnalysisRequest) -> TriageAssessment:
    """Run a full symptom-checker & triage assessment for the supplied inputs."""
    try:
        return await get_service().analyze(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Symptom analysis failed")
        raise HTTPException(
            status_code=500, detail=f"Symptom analysis failed: {exc}"
        ) from exc


@router.get("/catalog", response_model=SymptomCatalog)
async def catalog() -> SymptomCatalog:
    """Categorized symptom catalog + duration options for the picker."""
    try:
        return get_service().catalog()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to build symptom catalog")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/suggest")
async def suggest(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=20),
) -> dict:
    """Autocomplete suggestions for the symptom search box."""
    try:
        return {"suggestions": get_matcher().suggest(q, limit=limit)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Symptom autocomplete failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history", response_model=TriageHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> TriageHistoryPage:
    """Paginated list of past assessments (newest first)."""
    try:
        result = await get_service().list_history(page=page, page_size=page_size)
        return TriageHistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list symptom history")
        raise HTTPException(
            status_code=500, detail=f"Could not load history: {exc}"
        ) from exc


@router.delete("/history")
async def clear_history() -> dict:
    """Delete every stored assessment."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear symptom history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=TriageAssessment)
async def get_assessment(record_id: str) -> TriageAssessment:
    """Full stored report for a single past assessment."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"No symptom assessment: {record_id}"
        )
    return TriageAssessment(**report)
