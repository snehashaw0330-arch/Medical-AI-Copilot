"""Async persistence for Patient Context & Conversation Memory.

This is the only place in the module that talks to the database. Everything
is async (SQLAlchemy 2.0 async engine over aiosqlite), following the exact
engine/session/init pattern used by every other persisted module in this
codebase (see ``backend/history/service.py``).

Two contracts, by design:

* **Strict CRUD** (``upsert_profile``, ``get_profile``, ``list_profiles``,
  ``delete_profile_cascade``) — raises on failure, so the public create /
  read / list / delete endpoints can report real errors to the caller.
* **Best-effort** ``add_event`` — never raises. Other modules (and the
  Copilot chat integration) funnel writes through this, and a memory-store
  hiccup must never break an OCR run, an analysis, or a chat reply — the
  same contract as ``backend.history.service.save_ocr_record``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.patient_context.models import Base, PatientContextRecord, PatientEventRecord, utcnow

logger = logging.getLogger("patient_context.memory")

_engine = create_async_engine(
    settings.PATIENT_CONTEXT_DB_URL,
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
        logger.info(
            "Patient context store ready (%s)",
            settings.PATIENT_CONTEXT_DB_URL.split("://")[0],
        )


# ---------------------------------------------------------------------------
# Profile CRUD — strict, raises on failure
# ---------------------------------------------------------------------------
async def get_profile(patient_id: str) -> PatientContextRecord | None:
    await _ensure_init()
    async with _Session() as session:
        return await session.get(PatientContextRecord, patient_id)


async def upsert_profile(patient_id: str, **fields) -> PatientContextRecord:
    """Create or update a profile row. Only supplied fields are overwritten."""
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(PatientContextRecord, patient_id)
        now = utcnow()
        if row is None:
            row = PatientContextRecord(
                patient_id=patient_id,
                patient_name=fields.get("patient_name", patient_id),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        row.updated_at = now
        await session.commit()
        await session.refresh(row)
        return row


async def list_profiles() -> list[PatientContextRecord]:
    await _ensure_init()
    async with _Session() as session:
        stmt = select(PatientContextRecord).order_by(PatientContextRecord.updated_at.desc())
        return list((await session.execute(stmt)).scalars().all())


async def delete_profile_cascade(patient_id: str) -> int:
    """Delete a profile and all its events. Returns the number of events removed."""
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(PatientContextRecord, patient_id)
        if row is None:
            return -1
        count = await session.scalar(
            select(func.count(PatientEventRecord.id)).where(
                PatientEventRecord.patient_id == patient_id
            )
        ) or 0
        await session.execute(
            delete(PatientEventRecord).where(PatientEventRecord.patient_id == patient_id)
        )
        await session.delete(row)
        await session.commit()
        logger.info("Deleted patient context %s (%d events)", patient_id, count)
        return int(count)


# ---------------------------------------------------------------------------
# Events — best-effort writes, strict reads
# ---------------------------------------------------------------------------
async def add_event(
    patient_id: str,
    event_type: str,
    *,
    title: str = "",
    text: str = "",
    payload: dict | None = None,
    role: str | None = None,
    source_session_id: str | None = None,
    source_ref_id: str | None = None,
) -> PatientEventRecord | None:
    """Append one event. Best-effort: never raises, returns None on failure."""
    try:
        await _ensure_init()
        row = PatientEventRecord(
            id=uuid.uuid4().hex,
            patient_id=patient_id,
            event_type=event_type,
            role=role,
            title=title,
            text=text,
            payload=payload or {},
            source_session_id=source_session_id,
            source_ref_id=source_ref_id,
            created_at=utcnow(),
        )
        async with _Session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row
    except Exception:  # noqa: BLE001
        logger.exception("Failed to record patient_context event (%s/%s)", patient_id, event_type)
        return None


async def list_events(
    patient_id: str,
    event_type: str | None = None,
    *,
    limit: int = 50,
    newest_first: bool = True,
) -> list[PatientEventRecord]:
    await _ensure_init()
    async with _Session() as session:
        stmt = select(PatientEventRecord).where(PatientEventRecord.patient_id == patient_id)
        if event_type:
            stmt = stmt.where(PatientEventRecord.event_type == event_type)
        order = PatientEventRecord.created_at.desc() if newest_first else PatientEventRecord.created_at.asc()
        stmt = stmt.order_by(order).limit(limit)
        return list((await session.execute(stmt)).scalars().all())


async def count_events(patient_id: str, event_type: str | None = None) -> int:
    await _ensure_init()
    async with _Session() as session:
        stmt = select(func.count(PatientEventRecord.id)).where(
            PatientEventRecord.patient_id == patient_id
        )
        if event_type:
            stmt = stmt.where(PatientEventRecord.event_type == event_type)
        return int(await session.scalar(stmt) or 0)


async def recent_chat_events(patient_id: str, limit: int = 10) -> list[PatientEventRecord]:
    """Most recent chat_message events, oldest-first (ready for a transcript)."""
    rows = await list_events(patient_id, "chat_message", limit=limit, newest_first=True)
    return list(reversed(rows))
