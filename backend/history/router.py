"""FastAPI routes for the OCR History module.

All handlers are ``async`` and delegate to :mod:`backend.history.service`.
Static sub-paths (``/stats``, ``/medicines``) are declared before the dynamic
``/{record_id}`` route so they are matched first.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.history import service
from backend.history.schemas import (
    DeleteResult,
    HistoryDetail,
    HistoryPage,
    HistoryStats,
)

logger = logging.getLogger("history")

router = APIRouter(prefix="/history", tags=["ocr-history"])


@router.get("", response_model=HistoryPage)
async def list_history(
    q: str | None = Query(None, description="Search filename, OCR text or medicines"),
    medicine: str | None = Query(None, description="Filter to records containing this medicine"),
    status: str | None = Query(None, pattern="^(success|failed)$"),
    date_from: datetime | None = Query(None, description="ISO date/time lower bound (inclusive)"),
    date_to: datetime | None = Query(None, description="ISO date/time upper bound (inclusive)"),
    sort: str = Query("newest", pattern="^(newest|oldest|confidence)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> HistoryPage:
    """Paginated, filterable, sortable list of past OCR analyses."""
    try:
        result = await service.list_records(
            q=q, medicine=medicine, status=status,
            date_from=date_from, date_to=date_to,
            sort=sort, page=page, page_size=page_size,
        )
        return HistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list history")
        raise HTTPException(status_code=500, detail=f"Could not load history: {exc}") from exc


@router.get("/stats", response_model=HistoryStats)
async def history_stats() -> HistoryStats:
    """Aggregate statistics for the dashboard cards."""
    try:
        return HistoryStats(**await service.compute_stats())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute history stats")
        raise HTTPException(status_code=500, detail=f"Could not load stats: {exc}") from exc


@router.get("/medicines")
async def history_medicines() -> dict:
    """Distinct medicine names across all records (powers the filter dropdown)."""
    try:
        return {"medicines": await service.distinct_medicines()}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list distinct medicines")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{record_id}", response_model=HistoryDetail)
async def get_history(record_id: str) -> HistoryDetail:
    """Full detail for one record (OCR text, medicines, fields, drug info)."""
    record = await service.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No history record: {record_id}")
    return HistoryDetail(**record)


@router.get("/{record_id}/image")
async def get_history_image(record_id: str) -> FileResponse:
    """Serve the retained prescription image for a record."""
    path = await service.get_image_path(record_id)
    if not path:
        raise HTTPException(status_code=404, detail="No image stored for this record.")
    return FileResponse(path)


@router.delete("/{record_id}", response_model=DeleteResult)
async def delete_history(record_id: str) -> DeleteResult:
    """Delete a single history record (and its retained image)."""
    deleted = await service.delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No history record: {record_id}")
    return DeleteResult(deleted=1, message="Record deleted.")


@router.delete("", response_model=DeleteResult)
async def clear_history() -> DeleteResult:
    """Delete every history record (and all retained images)."""
    try:
        count = await service.clear_records()
        return DeleteResult(deleted=count, message=f"Cleared {count} record(s).")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear history")
        raise HTTPException(status_code=500, detail=f"Could not clear history: {exc}") from exc
