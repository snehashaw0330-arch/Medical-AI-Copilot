"""FastAPI routes for Patient Context & Conversation Memory (all async).

Endpoints
---------
* ``POST   /patient-context/create``            — create/update a patient profile.
* ``GET    /patient-context/history``            — list every remembered patient
  (also the frontend's patient-picker source).
* ``POST   /patient-context/{patient_id}/events`` — append one remembered fact
  (OCR result, medicine, disease prediction, interaction, report, summary or
  follow-up). Auto-creates the profile if missing and a patient_name is given.
* ``GET    /patient-context/{patient_id}``       — the full remembered bundle.
* ``DELETE /patient-context/{patient_id}``       — forget a patient (cascades).

Static routes are declared before the dynamic ``/{patient_id}`` routes so
``/patient-context/history`` is never swallowed by the ``{patient_id}`` path
parameter (the same ordering guard used by ``history``/``digital_twin``).
Every route wraps the service so a failure surfaces as an actionable HTTP
error rather than crashing the app.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.patient_context.schemas import (
    PatientContextCreateRequest,
    PatientContextDeleteResponse,
    PatientContextDetailResponse,
    PatientContextHistoryResponse,
    PatientContextProfile,
    PatientEventAppendRequest,
    PatientEventItem,
)
from backend.patient_context.service import get_service

logger = logging.getLogger("patient_context")

router = APIRouter(prefix="/patient-context", tags=["patient-context"])


@router.post("/create", response_model=PatientContextProfile)
async def create_context(req: PatientContextCreateRequest) -> PatientContextProfile:
    """Create a new patient context, or update it if the patient already exists."""
    try:
        return await get_service().create_context(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Patient context create failed")
        raise HTTPException(status_code=500, detail=f"Could not create patient context: {exc}") from exc


@router.get("/history", response_model=PatientContextHistoryResponse)
async def history() -> PatientContextHistoryResponse:
    """List every patient with a remembered context, most recently active first."""
    try:
        return await get_service().list_contexts()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Patient context history failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{patient_id}/events", response_model=PatientEventItem)
async def append_event(patient_id: str, req: PatientEventAppendRequest) -> PatientEventItem:
    """Append one remembered fact (OCR result, medicine, prediction, chat turn, ...)."""
    try:
        return await get_service().record_event(patient_id, req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Patient context event append failed")
        raise HTTPException(status_code=500, detail=f"Could not record event: {exc}") from exc


@router.get("/{patient_id}", response_model=PatientContextDetailResponse)
async def get_context(patient_id: str) -> PatientContextDetailResponse:
    """Return the full remembered bundle for one patient."""
    try:
        return await get_service().get_context(patient_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Patient context get failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{patient_id}", response_model=PatientContextDeleteResponse)
async def delete_context(patient_id: str) -> PatientContextDeleteResponse:
    """Forget a patient — deletes the profile and every remembered event."""
    try:
        return await get_service().delete_context(patient_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Patient context delete failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
