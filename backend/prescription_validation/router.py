"""FastAPI routes for the Prescription Validation module (all async).

Endpoints (Requirement 6)
-------------------------
* ``POST   /validation/check``     — validate a prescription / medicine list
* ``GET    /validation/history``   — paginated list of past validations
* ``DELETE /validation/history``   — clear stored validations
* ``GET    /validation/{id}``      — full stored report for one validation

The router never lets a validation failure crash the app: problems surface as
actionable 4xx/5xx responses with clear messages. The static ``/history`` route
is declared before the dynamic ``/{record_id}`` route so it is matched first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.prescription_validation.schemas import (
    ValidationHistoryPage,
    ValidationReport,
    ValidationRequest,
)
from backend.prescription_validation.service import get_service

logger = logging.getLogger("prescription_validation")

router = APIRouter(prefix="/validation", tags=["prescription-validation"])


@router.post("/check", response_model=ValidationReport)
async def check(req: ValidationRequest) -> ValidationReport:
    """Validate a prescription (or an edited medicine list) and grade its safety."""
    try:
        return await get_service().validate(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Prescription validation failed")
        raise HTTPException(
            status_code=500, detail=f"Prescription validation failed: {exc}"
        ) from exc


@router.get("/history", response_model=ValidationHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ValidationHistoryPage:
    """Paginated list of past validations (newest first)."""
    try:
        result = await get_service().list_history(page=page, page_size=page_size)
        return ValidationHistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list validation history")
        raise HTTPException(
            status_code=500, detail=f"Could not load history: {exc}"
        ) from exc


@router.delete("/history")
async def clear_history() -> dict:
    """Delete every stored validation."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear validation history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=ValidationReport)
async def get_report(record_id: str) -> ValidationReport:
    """Full stored report for a single past validation."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"No validation record: {record_id}"
        )
    return ValidationReport(**report)
