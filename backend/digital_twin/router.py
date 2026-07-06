"""FastAPI routes for the Digital Twin module (all async).

Endpoints
---------
* ``GET  /digital-twin/patients``        — patients that have a twin (UI picker)
* ``GET  /digital-twin/analytics``       — population-level analytics
* ``POST /digital-twin/recalculate``     — recompute one patient or everyone
* ``GET  /digital-twin/{patient_id}``    — the full Digital Twin for a patient

Static sub-paths are declared before the dynamic ``/{patient_id}`` route so they
are matched first. Failures surface as actionable HTTP errors; internal
enrichment/persistence failures degrade gracefully inside the service.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.digital_twin.schemas import (
    DigitalTwin,
    DigitalTwinAnalytics,
    PatientListItem,
    RecalculateRequest,
    RecalculateResult,
)
from backend.digital_twin.service import get_service

logger = logging.getLogger("digital_twin")

router = APIRouter(prefix="/digital-twin", tags=["digital-twin"])


@router.get("/patients", response_model=list[PatientListItem])
async def list_patients() -> list[PatientListItem]:
    """Every patient with at least one analysis on record (newest activity first)."""
    try:
        return await get_service().list_patients()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list digital-twin patients")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/analytics", response_model=DigitalTwinAnalytics)
async def analytics() -> DigitalTwinAnalytics:
    """Population-level analytics across all persisted twin snapshots."""
    try:
        return await get_service().analytics()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute digital-twin analytics")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/recalculate", response_model=RecalculateResult)
async def recalculate(req: RecalculateRequest | None = None) -> RecalculateResult:
    """Recompute the twin for one patient (``patient_id``) or all patients."""
    try:
        result = await get_service().recalculate(req.patient_id if req else None)
        return RecalculateResult(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Digital-twin recalculation failed")
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {exc}") from exc


@router.get("/{patient_id}", response_model=DigitalTwin)
async def get_twin(patient_id: str) -> DigitalTwin:
    """The full, live Digital Twin for a patient (computed fresh + snapshot saved)."""
    try:
        return await get_service().build_twin(patient_id, persist=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to build digital twin for %s", patient_id)
        raise HTTPException(status_code=500, detail=f"Could not build digital twin: {exc}") from exc
