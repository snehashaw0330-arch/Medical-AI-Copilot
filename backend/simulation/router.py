"""FastAPI routes for the AI Medical Simulation Engine (all async).

Endpoints
---------
* ``POST   /simulation/run``     — run a simulation (baseline + variant scenarios)
* ``GET    /simulation/history`` — paginated list of past simulations
* ``GET    /simulation/{id}``    — full stored report for one simulation
* ``DELETE /simulation/history`` — clear stored simulations

Every route wraps the service so a failure surfaces as an actionable HTTP error
rather than crashing the app. The static ``/history`` route is declared before the
dynamic ``/{record_id}`` route so it matches first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.simulation.schemas import (
    SimulationHistoryPage,
    SimulationReport,
    SimulationRequest,
)
from backend.simulation.service import get_service

logger = logging.getLogger("simulation")

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/run", response_model=SimulationReport)
async def run(req: SimulationRequest) -> SimulationReport:
    """Run a treatment simulation: baseline + every requested variant scenario."""
    if not req.baseline_medicines and not req.patient.symptoms:
        raise HTTPException(
            status_code=400,
            detail="Provide at least a baseline medicine list or patient symptoms.",
        )
    try:
        return await get_service().run(req)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Simulation run failed")
        raise HTTPException(status_code=500, detail=f"Simulation failed: {exc}") from exc


@router.get("/history", response_model=SimulationHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> SimulationHistoryPage:
    """Paginated list of past simulations (newest first)."""
    try:
        return SimulationHistoryPage(**await get_service().list_history(page=page, page_size=page_size))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list simulation history")
        raise HTTPException(status_code=500, detail=f"Could not load history: {exc}") from exc


@router.delete("/history")
async def clear_history() -> dict:
    """Delete every stored simulation."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear simulation history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=SimulationReport)
async def get_report(record_id: str) -> SimulationReport:
    """Full stored report for a single past simulation."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No simulation record: {record_id}")
    return SimulationReport(**report)
