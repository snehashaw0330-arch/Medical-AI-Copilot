"""FastAPI routes for the Drug Interaction Analysis module (all async).

Endpoints
---------
* ``POST /interactions/check``      — analyse a list of medicines
* ``GET  /interactions/history``    — paginated list of past analyses
* ``GET  /interactions/{id}``       — full stored report for one analysis
* ``GET  /interactions/health``     — knowledge-base readiness (ops/debug)
* ``DELETE /interactions/history``  — clear stored analyses

The router never lets an interaction failure crash the app: dataset or
dependency problems surface as actionable 4xx/5xx responses with clear messages.
``/history`` and ``/health`` are declared before the dynamic ``/{record_id}``
route so they are matched first.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.drug_interactions.schemas import (
    InteractionCheckRequest,
    InteractionHistoryPage,
    InteractionReport,
)
from backend.drug_interactions.service import build_source, get_service

logger = logging.getLogger("drug_interactions")

router = APIRouter(prefix="/interactions", tags=["drug-interactions"])


@router.get("/health")
async def interactions_health() -> dict:
    """Report whether the interaction knowledge base loads and how big it is."""
    try:
        knowledge = await get_service()._get_knowledge()
        return {
            "available": True,
            "source": type(build_source()).__name__,
            "profiles": len(knowledge.profiles),
            "pairwise_interactions": len(knowledge.pairs),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Interaction knowledge base failed to load")
        return {"available": False, "error": str(exc)}


@router.post("/check", response_model=InteractionReport)
async def check_interactions(req: InteractionCheckRequest) -> InteractionReport:
    """Analyse drug–drug interactions and per-drug warnings for a medicine list."""
    try:
        return await get_service().analyze(
            req.medicines,
            include_rag=req.include_rag,
            persist=req.persist,
            source_record_id=req.source_record_id,
        )
    except NotImplementedError as exc:
        # A not-yet-implemented data source (e.g. live OpenFDA) -> actionable 501.
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Interaction check failed")
        raise HTTPException(
            status_code=500, detail=f"Interaction analysis failed: {exc}"
        ) from exc


@router.get("/history", response_model=InteractionHistoryPage)
async def list_interaction_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> InteractionHistoryPage:
    """Paginated list of past interaction analyses (newest first)."""
    try:
        result = await get_service().list_history(page=page, page_size=page_size)
        return InteractionHistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list interaction history")
        raise HTTPException(
            status_code=500, detail=f"Could not load history: {exc}"
        ) from exc


@router.delete("/history")
async def clear_interaction_history() -> dict:
    """Delete every stored interaction analysis."""
    try:
        count = await get_service().clear_history()
        return {"deleted": count, "message": f"Cleared {count} record(s)."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear interaction history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=InteractionReport)
async def get_interaction(record_id: str) -> InteractionReport:
    """Full stored report for a single past analysis."""
    report = await get_service().get_history(record_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"No interaction record: {record_id}"
        )
    return InteractionReport(**report)
