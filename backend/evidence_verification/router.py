"""FastAPI routes for the Evidence Verification Engine (all async).

Endpoints
---------
* ``POST   /verification/check``    — verify a response (or generate + verify) vs evidence
* ``GET    /verification/history``  — paginated list of past verifications
* ``GET    /verification/{id}``     — full stored result for one verification
* ``DELETE /verification/history``  — clear stored verifications

Every route wraps the service so a failure surfaces as an actionable HTTP error
rather than crashing the app. The static ``/history`` route is declared before the
dynamic ``/{record_id}`` route so it matches first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.evidence_verification.schemas import (
    VerificationHistoryPage,
    VerificationRequest,
    VerificationResult,
)
from backend.evidence_verification.service import get_service

logger = logging.getLogger("evidence_verification")

router = APIRouter(prefix="/verification", tags=["evidence-verification"])


@router.post("/check", response_model=VerificationResult)
async def check(req: VerificationRequest) -> VerificationResult:
    """Verify an AI response against retrieved medical evidence.

    Supply ``response`` to verify existing text, or omit it (with
    ``generate_if_missing``) to have the RAG knowledge base answer ``question``
    and verify that answer.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="A question is required.")
    if not req.response and not req.generate_if_missing:
        raise HTTPException(
            status_code=400,
            detail="Provide a response to verify, or enable generate_if_missing.",
        )
    try:
        return await get_service().check(req)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Verification failed")
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}") from exc


@router.get("/history", response_model=VerificationHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> VerificationHistoryPage:
    """Paginated list of past verifications (newest first)."""
    try:
        return VerificationHistoryPage(**await get_service().list_history(page=page, page_size=page_size))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list verification history")
        raise HTTPException(status_code=500, detail=f"Could not load history: {exc}") from exc


@router.delete("/history")
async def clear_history() -> dict:
    """Delete every stored verification."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear verification history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=VerificationResult)
async def get_report(record_id: str) -> VerificationResult:
    """Full stored result for a single past verification."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No verification record: {record_id}")
    return VerificationResult(**report)
