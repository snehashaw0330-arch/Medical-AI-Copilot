"""Shared async database infrastructure for the AI Governance store.

One async engine + session factory backs all four governance tables (decision
traces, audit logs, model registry, dataset registry). Centralising it here keeps
the tracker, audit logger and registries decoupled from connection management
(they receive the session factory via dependency injection) and guarantees a
single, idempotent table-creation path.

Same async URL contract as every other store in the project: defaults to a local
SQLite file, point ``AI_GOVERNANCE_DB_URL`` (or the shared ``DATABASE_URL``) at
PostgreSQL in production with no code changes.
"""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.ai_governance.models import Base
from backend.config import settings

logger = logging.getLogger("ai_governance")

engine = create_async_engine(
    settings.AI_GOVERNANCE_DB_URL, echo=False, pool_pre_ping=True, future=True
)
Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

_db_lock = asyncio.Lock()
_db_ready = False


async def ensure_db() -> None:
    """Create the governance tables once (idempotent, concurrency-safe)."""
    global _db_ready
    if _db_ready:
        return
    async with _db_lock:
        if _db_ready:
            return
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_ready = True
        logger.info(
            "AI-governance store ready (%s)",
            settings.AI_GOVERNANCE_DB_URL.split("://")[0],
        )


# --------------------------------------------------------------------------
# Sensitive-data masking (Requirement: SECURITY)
# --------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\b(?:\+?\d[\d\s-]{7,}\d)\b")
_LONG_NUM = re.compile(r"\b\d{6,}\b")  # MRNs, long ids


def mask_phi(text: str | None) -> str | None:
    """Redact obvious PHI (emails, phone numbers, long identifiers) from free text.

    Deliberately conservative — it protects exports/logs without mangling clinical
    content. Names are masked separately (``mask_name``) where the schema knows a
    field is a name.
    """
    if not text:
        return text
    out = _EMAIL.sub("[email]", text)
    out = _PHONE.sub("[phone]", out)
    out = _LONG_NUM.sub("[id]", out)
    return out


def mask_name(name: str | None) -> str | None:
    """Mask a person's name to initials + redaction ('John Doe' → 'J. D.')."""
    if not name:
        return name
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    if not parts:
        return name
    return " ".join(f"{p[0].upper()}." for p in parts)
