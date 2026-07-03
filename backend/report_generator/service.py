"""Business logic + async persistence for the Medical Report Generator.

This is the only layer that touches the database and the filesystem. It:

1. **Builds** a structured :class:`ReportContent` from an OCR result (delegating
   to :mod:`report_builder`).
2. **Retains** a copy of the prescription image (like the OCR-history store) so
   reports remain self-contained even if the original upload is gone.
3. **Persists** the report (async SQLAlchemy over aiosqlite; PostgreSQL-ready).
4. **Exports** on demand as JSON, HTML (:mod:`templates`) or PDF
   (:mod:`pdf_generator`) — CPU-bound rendering runs in a worker thread.

Every public entry point logs and degrades gracefully. Persistence is best-effort
(never raises) so a report failure can never break the OCR flow that triggers it.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.report_generator import report_builder, templates
from backend.report_generator.models import Base, ReportRecord, utcnow
from backend.report_generator.pdf_generator import render_pdf
from backend.report_generator.schemas import ReportContent, ReportGenerateRequest

logger = logging.getLogger("report_generator")


# ==========================================================================
# Persistence (async; same contract as the other module stores)
# ==========================================================================
_engine = create_async_engine(
    settings.REPORTS_DB_URL, echo=False, pool_pre_ping=True, future=True
)
_Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession
)
_db_init_lock = asyncio.Lock()
_db_ready = False


async def _ensure_db() -> None:
    """Create the reports table on first use (idempotent, race-safe)."""
    global _db_ready
    if _db_ready:
        return
    async with _db_init_lock:
        if _db_ready:
            return
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_ready = True
        logger.info(
            "Medical-report store ready (%s)", settings.REPORTS_DB_URL.split("://")[0]
        )


# ==========================================================================
# Image retention (best-effort — a missing image never breaks a report)
# ==========================================================================
_MIME_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/webp": ".webp", "image/bmp": ".bmp", "image/tiff": ".tiff",
}


def _persist_image_from_path(src_path: str, report_id: str) -> str | None:
    """Copy an on-disk image into the report store. Returns the dest path."""
    try:
        suffix = Path(src_path).suffix.lower() or ".png"
        dest = Path(settings.REPORTS_IMAGE_DIR) / f"{report_id}{suffix}"
        shutil.copyfile(src_path, dest)
        return str(dest)
    except Exception:  # noqa: BLE001 — image retention is best-effort
        logger.exception("Failed to retain report image (from path) for %s", report_id)
        return None


def _persist_image_from_data_url(data_url: str, report_id: str) -> str | None:
    """Decode a base64 ``data:`` URL and write it into the report store."""
    try:
        header, _, b64 = data_url.partition(",")
        if not b64:
            return None
        mime = header.split(";")[0].removeprefix("data:").strip().lower()
        suffix = _MIME_EXT.get(mime, ".png")
        dest = Path(settings.REPORTS_IMAGE_DIR) / f"{report_id}{suffix}"
        dest.write_bytes(base64.b64decode(b64))
        return str(dest)
    except Exception:  # noqa: BLE001 — image retention is best-effort
        logger.exception("Failed to retain report image (from data URL) for %s", report_id)
        return None


def _image_data_uri(path: str) -> str | None:
    """Read an on-disk image and return it as a base64 ``data:`` URI (for HTML)."""
    try:
        suffix = Path(path).suffix.lower()
        mime = next((m for m, e in _MIME_EXT.items() if e == suffix), "image/png")
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception:  # noqa: BLE001
        return None


def _timestamp(dt: datetime) -> str:
    """Human-readable UTC timestamp for report headers."""
    return dt.strftime("%d %b %Y, %H:%M UTC")


# ==========================================================================
# Service
# ==========================================================================
class ReportService:
    """Generate, persist, list, export and delete medical reports."""

    # -- shared save path --------------------------------------------------
    async def _save(
        self,
        ocr_result: dict,
        *,
        filename: str | None,
        processing_time: float,
        source_record_id: str | None,
        image_src: str | None = None,
        image_data_url: str | None = None,
        persist: bool = True,
    ) -> dict:
        """Build a report, retain its image, persist it, and return the detail dict."""
        record_id = uuid.uuid4().hex
        created = utcnow()

        # Retain the prescription image (path copy or data-URL decode).
        image_path: str | None = None
        if image_src:
            image_path = await asyncio.to_thread(
                _persist_image_from_path, image_src, record_id
            )
        elif image_data_url:
            image_path = await asyncio.to_thread(
                _persist_image_from_data_url, image_data_url, record_id
            )

        # Assemble the structured content (pure, CPU-cheap).
        content = report_builder.build_content(
            ocr_result,
            filename=filename,
            processing_time=processing_time,
            has_image=bool(image_path),
            generated_at=created,
            timestamp=_timestamp(created),
        )
        projection = report_builder.record_projection(content)

        if persist:
            try:
                await _ensure_db()
                row = ReportRecord(
                    id=record_id,
                    created_at=created,
                    source_record_id=source_record_id,
                    filename=filename,
                    image_path=image_path,
                    processing_time=round(float(processing_time), 3),
                    content=content.model_dump(mode="json"),
                    **projection,
                )
                async with _Session() as session:
                    session.add(row)
                    await session.commit()
                logger.info(
                    "Saved medical report %s (%d medicines, risk=%s)",
                    record_id, projection["medicine_count"], projection.get("risk_level"),
                )
            except Exception:  # noqa: BLE001 — persistence is best-effort
                logger.exception("Failed to save medical report")
                # Clean up an orphaned image if the row didn't persist.
                if image_path:
                    await asyncio.to_thread(_safe_remove, image_path)

        return {
            "id": record_id,
            "created_at": created,
            "source_record_id": source_record_id,
            "content": content.model_dump(mode="json"),
        }

    # -- public generate (router) -----------------------------------------
    async def generate(self, req: ReportGenerateRequest) -> dict:
        """Generate a report from a ``ReportGenerateRequest`` (API entry point)."""
        return await self._save(
            req.ocr_result or {},
            filename=req.filename,
            processing_time=req.processing_time,
            source_record_id=req.source_record_id,
            image_data_url=req.image_data_url,
            persist=req.persist,
        )

    # -- OCR auto-generate hook (best-effort) ------------------------------
    async def generate_from_ocr(
        self,
        ocr_result: dict,
        *,
        filename: str | None,
        processing_time: float,
        image_src: str | None,
        source_record_id: str | None = None,
    ) -> str | None:
        """Generate + persist a report straight from the OCR flow. Never raises."""
        try:
            detail = await self._save(
                ocr_result,
                filename=filename,
                processing_time=processing_time,
                source_record_id=source_record_id,
                image_src=image_src,
                persist=True,
            )
            return detail["id"]
        except Exception:  # noqa: BLE001 — must never break OCR
            logger.exception("Auto report generation failed (OCR unaffected)")
            return None

    # -- reads -------------------------------------------------------------
    @staticmethod
    def _apply_filters(stmt, *, q, patient, date_from, date_to):
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                func.lower(ReportRecord.filename).like(like)
                | func.lower(ReportRecord.patient_name).like(like)
                | ReportRecord.medicine_names.like(like)
            )
        if patient:
            stmt = stmt.where(func.lower(ReportRecord.patient_name).like(f"%{patient.lower()}%"))
        if date_from:
            stmt = stmt.where(ReportRecord.created_at >= date_from)
        if date_to:
            stmt = stmt.where(ReportRecord.created_at <= date_to)
        return stmt

    async def list_reports(
        self, *, q=None, patient=None, date_from=None, date_to=None,
        page: int = 1, page_size: int = 10,
    ) -> dict:
        """Filtered, paginated list of reports (newest first)."""
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        filters = dict(q=q, patient=patient, date_from=date_from, date_to=date_to)
        async with _Session() as session:
            total = await session.scalar(
                self._apply_filters(select(func.count(ReportRecord.id)), **filters)
            ) or 0
            stmt = (
                self._apply_filters(select(ReportRecord), **filters)
                .order_by(ReportRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return {
            "items": [r.item() for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "pages": (int(total) + page_size - 1) // page_size,
        }

    async def get_report(self, report_id: str) -> dict | None:
        """Full stored report detail, or None if missing."""
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(ReportRecord, report_id)
            return row.detail() if row else None

    async def _get_row(self, report_id: str) -> ReportRecord | None:
        await _ensure_db()
        async with _Session() as session:
            return await session.get(ReportRecord, report_id)

    async def get_image_path(self, report_id: str) -> str | None:
        row = await self._get_row(report_id)
        if row and row.image_path and Path(row.image_path).exists():
            return row.image_path
        return None

    # -- exports -----------------------------------------------------------
    async def _content_and_image(self, report_id: str):
        row = await self._get_row(report_id)
        if not row:
            return None, None
        content = ReportContent(**(row.content or {}))
        image_path = row.image_path if (row.image_path and Path(row.image_path).exists()) else None
        return content, image_path

    async def export_json(self, report_id: str) -> dict | None:
        row = await self._get_row(report_id)
        return row.detail() if row else None

    async def export_html(self, report_id: str) -> str | None:
        content, image_path = await self._content_and_image(report_id)
        if content is None:
            return None
        image_uri = await asyncio.to_thread(_image_data_uri, image_path) if image_path else None
        return await asyncio.to_thread(templates.render_html, content, image_data_uri=image_uri)

    async def export_pdf(self, report_id: str) -> bytes | None:
        content, image_path = await self._content_and_image(report_id)
        if content is None:
            return None
        return await asyncio.to_thread(render_pdf, content, image_path=image_path)

    # -- delete ------------------------------------------------------------
    async def delete_report(self, report_id: str) -> bool:
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(ReportRecord, report_id)
            if not row:
                return False
            image_path = row.image_path
            await session.delete(row)
            await session.commit()
        if image_path:
            await asyncio.to_thread(_safe_remove, image_path)
        logger.info("Deleted medical report %s", report_id)
        return True

    async def clear_reports(self) -> int:
        await _ensure_db()
        async with _Session() as session:
            paths = (await session.scalars(select(ReportRecord.image_path))).all()
            count = await session.scalar(select(func.count(ReportRecord.id))) or 0
            await session.execute(delete(ReportRecord))
            await session.commit()
        for p in paths:
            if p:
                await asyncio.to_thread(_safe_remove, p)
        logger.info("Cleared medical reports (%d records)", count)
        return int(count)

    # -- stats -------------------------------------------------------------
    async def compute_stats(self) -> dict:
        """Aggregate statistics for the dashboard cards (Requirement 8)."""
        await _ensure_db()
        # UTC midnight today (created_at is stored naive-UTC).
        now = utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with _Session() as session:
            total = await session.scalar(select(func.count(ReportRecord.id))) or 0
            today = await session.scalar(
                select(func.count(ReportRecord.id)).where(
                    ReportRecord.created_at >= start_of_day
                )
            ) or 0
            avg_conf = await session.scalar(select(func.avg(ReportRecord.overall_confidence)))
            high_risk = await session.scalar(
                select(func.count(ReportRecord.id)).where(
                    ReportRecord.risk_level.in_(["high", "critical"])
                )
            ) or 0
        return {
            "total_reports": int(total),
            "reports_today": int(today),
            "average_confidence": round(float(avg_conf or 0.0), 4),
            "high_risk_reports": int(high_risk),
        }


def _safe_remove(path: str | None) -> None:
    if path:
        try:
            os.remove(path)
        except OSError:
            pass  # already gone — nothing to do


# Process-wide singleton.
_SERVICE: ReportService | None = None


def get_service() -> ReportService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ReportService()
    return _SERVICE


# Convenience coroutine used by the OCR pipeline for auto-generation.
async def generate_from_ocr(
    ocr_result: dict,
    *,
    filename: str | None,
    processing_time: float,
    image_src: str | None,
    source_record_id: str | None = None,
) -> str | None:
    """Module-level shortcut around :meth:`ReportService.generate_from_ocr`."""
    return await get_service().generate_from_ocr(
        ocr_result,
        filename=filename,
        processing_time=processing_time,
        image_src=image_src,
        source_record_id=source_record_id,
    )
