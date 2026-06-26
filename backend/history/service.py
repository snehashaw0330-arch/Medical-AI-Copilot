"""Business logic + async persistence for the OCR History module.

This is the only place that talks to the database. The FastAPI router and the
OCR pipeline call these coroutines; everything is async (SQLAlchemy 2.0 async
engine over aiosqlite) so the request thread is never blocked on I/O.

Swapping SQLite for PostgreSQL is a configuration change only: set
``DATABASE_URL=postgresql+asyncpg://...`` and install ``asyncpg``. No code here
changes — the model column types and queries are portable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.history.models import Base, OCRRecord, utcnow

logger = logging.getLogger("history")

# --- Engine / session (created once, reused for the process lifetime) --------
# ``pool_pre_ping`` keeps long-lived PostgreSQL connections healthy; it is a
# harmless no-op for SQLite.
_engine = create_async_engine(
    settings.HISTORY_DB_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
)
_Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession
)

_init_lock = asyncio.Lock()
_initialized = False


async def _ensure_init() -> None:
    """Create tables on first use (idempotent, race-safe)."""
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if _initialized:  # re-check inside the lock
            return
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _initialized = True
        logger.info("OCR history store ready (%s)", settings.HISTORY_DB_URL.split("://")[0])


# ---------------------------------------------------------------------------
# Write path — called by the OCR endpoint after every analysis
# ---------------------------------------------------------------------------
def _persist_image(src_path: str, record_id: str) -> str | None:
    """Copy the analyzed image into the history store. Returns the dest path."""
    try:
        suffix = Path(src_path).suffix.lower() or ".png"
        dest = Path(settings.HISTORY_IMAGE_DIR) / f"{record_id}{suffix}"
        shutil.copyfile(src_path, dest)
        return str(dest)
    except Exception:  # noqa: BLE001 — image retention is best-effort
        logger.exception("Failed to persist history image for %s", record_id)
        return None


def _row_from_result(record_id: str, result: Any) -> dict:
    """Map a PrescriptionResult (duck-typed) onto OCRRecord columns."""
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    medicines = data.get("medicines", []) or []
    names = [m.get("name") for m in medicines if m.get("name")]
    return {
        "raw_text": data.get("raw_text", "") or "",
        "medicines": medicines,
        "medicine_names": ",".join(n.lower() for n in names),
        "medicine_count": len(names),
        "fields": data.get("fields", {}) or {},
        "doctor_notes": data.get("doctor_notes", []) or [],
        "confidence": float(data.get("overall_confidence", 0.0) or 0.0),
        "engine": data.get("best_engine"),
        "provider": data.get("provider"),
    }


async def save_ocr_record(
    image_src: str | None,
    filename: str | None,
    *,
    result: Any | None = None,
    processing_time: float = 0.0,
    error: str | None = None,
) -> str | None:
    """Persist one OCR analysis (success or failure).

    Best-effort: never raises, so a history failure can never break OCR. Returns
    the new record id, or ``None`` if saving failed.
    """
    try:
        await _ensure_init()
        record_id = uuid.uuid4().hex
        image_path = (
            await asyncio.to_thread(_persist_image, image_src, record_id)
            if image_src
            else None
        )

        row: dict = {
            "id": record_id,
            "created_at": utcnow(),
            "filename": filename,
            "image_path": image_path,
            "processing_time": round(float(processing_time), 3),
            "status": "failed" if error else "success",
            "error": error,
        }
        if result is not None and not error:
            row.update(_row_from_result(record_id, result))

        async with _Session() as session:
            session.add(OCRRecord(**row))
            await session.commit()
        logger.info("Saved OCR history record %s (%s)", record_id, row["status"])
        return record_id
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save OCR history record")
        return None


# ---------------------------------------------------------------------------
# Read path — list / detail / stats
# ---------------------------------------------------------------------------
def _apply_filters(stmt, *, q, medicine, status, date_from, date_to):
    """Attach optional WHERE clauses shared by the list and count queries."""
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(OCRRecord.filename).like(like)
            | func.lower(OCRRecord.raw_text).like(like)
            | OCRRecord.medicine_names.like(like)
        )
    if medicine:
        stmt = stmt.where(OCRRecord.medicine_names.like(f"%{medicine.lower()}%"))
    if status:
        stmt = stmt.where(OCRRecord.status == status)
    if date_from:
        stmt = stmt.where(OCRRecord.created_at >= date_from)
    if date_to:
        stmt = stmt.where(OCRRecord.created_at <= date_to)
    return stmt


async def list_records(
    *,
    q: str | None = None,
    medicine: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """Return a filtered, sorted, paginated page of history items."""
    await _ensure_init()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    filters = dict(q=q, medicine=medicine, status=status, date_from=date_from, date_to=date_to)

    async with _Session() as session:
        total = await session.scalar(
            _apply_filters(select(func.count(OCRRecord.id)), **filters)
        ) or 0

        order = {
            "oldest": OCRRecord.created_at.asc(),
            "confidence": OCRRecord.confidence.desc(),
        }.get(sort, OCRRecord.created_at.desc())

        stmt = _apply_filters(select(OCRRecord), **filters).order_by(order)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(stmt)).scalars().all()

    return {
        "items": [r.summary() for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


async def get_record(record_id: str) -> dict | None:
    """Return the full detail for one record, or ``None`` if missing."""
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(OCRRecord, record_id)
        return row.detail() if row else None


async def get_image_path(record_id: str) -> str | None:
    """Return the on-disk image path for a record (if one was retained)."""
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(OCRRecord, record_id)
        if row and row.image_path and Path(row.image_path).exists():
            return row.image_path
    return None


async def distinct_medicines(limit: int = 200) -> list[str]:
    """Distinct medicine names across all records (for the filter dropdown)."""
    await _ensure_init()
    async with _Session() as session:
        rows = await session.scalars(
            select(OCRRecord.medicine_names).where(OCRRecord.medicine_names != "")
        )
    names: set[str] = set()
    for blob in rows:
        names.update(n for n in blob.split(",") if n)
    return sorted(names)[:limit]


async def compute_stats() -> dict:
    """Aggregate statistics for the dashboard cards."""
    await _ensure_init()
    async with _Session() as session:
        total = await session.scalar(select(func.count(OCRRecord.id))) or 0
        successful = await session.scalar(
            select(func.count(OCRRecord.id)).where(OCRRecord.status == "success")
        ) or 0
        avg_conf = await session.scalar(
            select(func.avg(OCRRecord.confidence)).where(OCRRecord.status == "success")
        )
        avg_time = await session.scalar(
            select(func.avg(OCRRecord.processing_time)).where(OCRRecord.status == "success")
        )
        total_meds = await session.scalar(select(func.sum(OCRRecord.medicine_count))) or 0

    return {
        "total_analyses": int(total),
        "successful_analyses": int(successful),
        "failed_analyses": int(total - successful),
        "average_confidence": round(float(avg_conf or 0.0), 3),
        "average_processing_time": round(float(avg_time or 0.0), 3),
        "total_medicines": int(total_meds),
    }


# ---------------------------------------------------------------------------
# Delete path
# ---------------------------------------------------------------------------
def _remove_image(image_path: str | None) -> None:
    if image_path:
        try:
            os.remove(image_path)
        except OSError:
            pass  # already gone — nothing to do


async def delete_record(record_id: str) -> bool:
    """Delete one record and its retained image. Returns False if not found."""
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(OCRRecord, record_id)
        if not row:
            return False
        image_path = row.image_path
        await session.delete(row)
        await session.commit()
    await asyncio.to_thread(_remove_image, image_path)
    logger.info("Deleted OCR history record %s", record_id)
    return True


async def clear_records() -> int:
    """Delete every record (and its image). Returns the number removed."""
    await _ensure_init()
    async with _Session() as session:
        paths = (await session.scalars(select(OCRRecord.image_path))).all()
        count = await session.scalar(select(func.count(OCRRecord.id))) or 0
        await session.execute(delete(OCRRecord))
        await session.commit()
    for p in paths:
        await asyncio.to_thread(_remove_image, p)
    logger.info("Cleared OCR history (%d records)", count)
    return int(count)
