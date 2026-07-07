"""Audit logger — an immutable record of every API request.

Two responsibilities:

* :class:`AuditLogger` — persists and queries audit-log rows. Writes are
  **background, best-effort and non-blocking**: a logging failure can never break
  or slow the request being audited (fire-and-forget via ``asyncio.create_task``).
  Sensitive fields (prompt, sources) are PHI-masked before they hit the store.
* :class:`AuditMiddleware` — a Starlette middleware that times every request and
  schedules exactly one audit row for it (method, path, status, duration, user,
  and any error). Added in ``app.py`` so it observes the whole application without
  touching any existing route.

Backed by the shared governance engine; the search/query surface powers the Audit
Logs page and the CSV/JSON/PDF export.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from backend.ai_governance.db import ensure_db, mask_phi
from backend.ai_governance.models import AuditLogRecord
from backend.ai_governance.schemas import AuditLogItem, AuditLogPage

logger = logging.getLogger("ai_governance")

# Paths we deliberately do not audit (health checks, docs, and the audit surface
# itself — auditing the audit reader would create noise/recursion).
_SKIP_PREFIXES = ("/governance/audit-logs", "/docs", "/openapi", "/redoc", "/favicon")


class AuditLogger:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._Session = session_factory

    async def log(
        self,
        *,
        user: str = "system",
        method: str = "",
        api: str = "",
        status_code: int = 0,
        processing_time_ms: float = 0.0,
        model_used: str | None = None,
        prompt: str | None = None,
        sources: list[str] | None = None,
        warnings: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        """Persist one audit row. Best-effort: swallows all errors."""
        try:
            await ensure_db()
            async with self._Session() as session:
                session.add(AuditLogRecord(
                    user=user, method=method, api=api, status_code=status_code,
                    processing_time_ms=round(processing_time_ms, 2),
                    model_used=model_used,
                    prompt=mask_phi(prompt) if prompt else None,
                    sources=[mask_phi(s) for s in (sources or [])],
                    warnings=warnings or [],
                    error=mask_phi(error) if error else None,
                ))
                await session.commit()
        except Exception:  # noqa: BLE001 — auditing must never break a request
            logger.debug("Audit log write failed (request unaffected)", exc_info=True)

    async def search(
        self,
        *,
        user: str | None = None,
        api: str | None = None,
        status_code: int | None = None,
        method: str | None = None,
        errors_only: bool = False,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditLogPage:
        await ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 500))
        conds = []
        if user:
            conds.append(AuditLogRecord.user == user)
        if api:
            conds.append(AuditLogRecord.api.ilike(f"%{api}%"))
        if status_code is not None:
            conds.append(AuditLogRecord.status_code == status_code)
        if method:
            conds.append(AuditLogRecord.method == method.upper())
        if errors_only:
            conds.append(AuditLogRecord.error.is_not(None))
        if date_from:
            conds.append(AuditLogRecord.created_at >= date_from)
        if date_to:
            conds.append(AuditLogRecord.created_at <= date_to)

        async with self._Session() as session:
            total = (await session.execute(
                select(func.count(AuditLogRecord.id)).where(*conds)
            )).scalar_one()
            rows = (await session.execute(
                select(AuditLogRecord).where(*conds)
                .order_by(AuditLogRecord.created_at.desc())
                .offset((page - 1) * page_size).limit(page_size)
            )).scalars().all()

        items = [AuditLogItem(**r.item()) for r in rows]
        pages = (total + page_size - 1) // page_size
        return AuditLogPage(items=items, total=total, page=page, page_size=page_size, pages=pages)

    async def all_for_export(self, limit: int = 5000) -> list[AuditLogItem]:
        await ensure_db()
        async with self._Session() as session:
            rows = (await session.execute(
                select(AuditLogRecord).order_by(AuditLogRecord.created_at.desc()).limit(limit)
            )).scalars().all()
        return [AuditLogItem(**r.item()) for r in rows]

    async def count(self, *, errors_only: bool = False) -> int:
        await ensure_db()
        conds = [AuditLogRecord.error.is_not(None)] if errors_only else []
        async with self._Session() as session:
            return (await session.execute(
                select(func.count(AuditLogRecord.id)).where(*conds)
            )).scalar_one()


class AuditMiddleware(BaseHTTPMiddleware):
    """Times every request and schedules one background audit row for it."""

    def __init__(self, app: ASGIApp, audit_logger: AuditLogger) -> None:
        super().__init__(app)
        self._audit = audit_logger

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        error: str | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:  # noqa: BLE001 — re-raised after we note it
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            path = request.url.path
            if not any(path.startswith(p) for p in _SKIP_PREFIXES):
                elapsed_ms = (time.perf_counter() - started) * 1000
                user = request.headers.get("x-user") or (
                    request.client.host if request.client else "anonymous")
                # Fire-and-forget: never awaited, never blocks the response.
                import asyncio

                asyncio.create_task(self._audit.log(
                    user=user, method=request.method, api=path,
                    status_code=status_code, processing_time_ms=elapsed_ms,
                    warnings=(["request failed"] if status_code >= 500 else []),
                    error=error,
                ))
