"""Pydantic response models for the OCR History API (the frontend contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HistoryItem(BaseModel):
    """Lightweight record used in the paginated list view."""

    id: str
    created_at: datetime
    filename: str | None = None
    medicine_count: int = 0
    medicine_names: list[str] = []
    confidence: float = 0.0          # 0..1
    engine: str | None = None
    processing_time: float = 0.0     # seconds
    status: str = "success"          # "success" | "failed"
    has_image: bool = False


class HistoryDetail(HistoryItem):
    """Full record returned by ``GET /history/{id}``."""

    raw_text: str = ""
    medicines: list[dict[str, Any]] = []
    fields: dict[str, Any] = {}
    doctor_notes: list[str] = []
    provider: str | None = None
    error: str | None = None


class HistoryPage(BaseModel):
    """A page of history items plus pagination metadata."""

    items: list[HistoryItem] = []
    total: int = 0            # total rows matching the filters
    page: int = 1
    page_size: int = 10
    pages: int = 0            # total number of pages for the current filters


class HistoryStats(BaseModel):
    """Aggregate statistics for the dashboard cards."""

    total_analyses: int = 0
    successful_analyses: int = 0
    failed_analyses: int = 0
    average_confidence: float = 0.0       # 0..1, over successful records
    average_processing_time: float = 0.0  # seconds, over successful records
    total_medicines: int = 0


class DeleteResult(BaseModel):
    """Outcome of a delete / clear operation."""

    deleted: int = 0
    message: str = ""
