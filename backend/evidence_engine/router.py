"""FastAPI routes for the Evidence-Based Medical Response Engine (all async).

Endpoints
---------
* ``POST   /evidence/query``    — retrieve evidence and generate a grounded, cited response
* ``POST   /evidence/chat``     — same pipeline, but session-aware (remembers recent turns)
* ``GET    /evidence/history``  — paginated list of past queries/chats
* ``GET    /evidence/{id}``     — full stored result for one past query
* ``DELETE /evidence/history``  — clear stored history

Every route wraps the service so a failure surfaces as an actionable HTTP
error rather than crashing the app. The static ``/history`` route is declared
before the dynamic ``/{record_id}`` route so it matches first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.evidence_engine.schemas import (
    EvidenceChatRequest,
    EvidenceHistoryPage,
    EvidenceQueryRequest,
    EvidenceResponse,
)
from backend.evidence_engine.service import get_service

logger = logging.getLogger("evidence_engine")

router = APIRouter(prefix="/evidence", tags=["evidence-engine"])


@router.post("/query", response_model=EvidenceResponse)
async def query(req: EvidenceQueryRequest) -> EvidenceResponse:
    """Retrieve medical evidence for ``query`` and generate a grounded, cited response."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="A query is required.")
    try:
        return await get_service().aquery(req)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Evidence query failed")
        raise HTTPException(status_code=500, detail=f"Evidence query failed: {exc}") from exc


@router.post("/chat", response_model=EvidenceResponse)
async def chat(req: EvidenceChatRequest) -> EvidenceResponse:
    """Evidence-grounded chat turn. Pass the same ``session_id`` back for follow-ups."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="A message is required.")
    try:
        return await get_service().achat(req)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Evidence chat failed")
        raise HTTPException(status_code=500, detail=f"Evidence chat failed: {exc}") from exc


@router.get("/history", response_model=EvidenceHistoryPage)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> EvidenceHistoryPage:
    """Paginated list of past evidence queries/chats (newest first)."""
    try:
        return EvidenceHistoryPage(**await get_service().list_history(page=page, page_size=page_size))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list evidence history")
        raise HTTPException(status_code=500, detail=f"Could not load history: {exc}") from exc


@router.delete("/history")
async def clear_history() -> dict:
    """Delete every stored evidence query/chat record."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear evidence history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=EvidenceResponse)
async def get_report(record_id: str) -> EvidenceResponse:
    """Full stored result for a single past evidence query."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No evidence record: {record_id}")
    return EvidenceResponse(**report)
