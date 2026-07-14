"""Business logic + async persistence for Medical Document Intelligence.

Orchestrates the full workflow (Upload -> Detect Type -> Extract Text ->
Parse Structured Data -> RAG -> Clinical Summary -> Highlight Abnormal
Findings -> AI Explanation) and persists every analysis, mirroring
``backend/history/service.py`` and ``backend/report_generator/service.py``
(async SQLAlchemy over aiosqlite, PostgreSQL-ready via ``DATABASE_URL``).

Every public entry point degrades gracefully: persistence is best-effort and
never raises, so a storage failure can never break an analysis response.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
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
from backend.document_intelligence import clinical_summary, document_classifier, lab_report_analyzer, report_parser
from backend.document_intelligence.models import Base, DocumentRecord, utcnow
from backend.document_intelligence.schemas import (
    LAB_DOCUMENT_TYPES,
    DocumentAnalysisResult,
    DocumentClassification,
    DocumentFields,
    DocumentType,
)

logger = logging.getLogger("document_intelligence")

# --- Engine / session (created once, reused for the process lifetime) ------
_engine = create_async_engine(
    settings.DOCUMENT_INTELLIGENCE_DB_URL, echo=False, pool_pre_ping=True, future=True
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
        if _initialized:
            return
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _initialized = True
        logger.info(
            "Document Intelligence store ready (%s)",
            settings.DOCUMENT_INTELLIGENCE_DB_URL.split("://")[0],
        )


# ---------------------------------------------------------------------------
# Analysis (the workflow itself)
# ---------------------------------------------------------------------------
async def analyze_document(
    path: str,
    filename: str | None,
    *,
    document_type_override: DocumentType | None = None,
    provider_name: str | None = None,
) -> DocumentAnalysisResult:
    """Run the full document-intelligence workflow on an uploaded file."""
    started = time.perf_counter()
    suffix = Path(path).suffix.lower()

    # Step 3: extract text (OCR for images, pypdf/OCR for PDFs).
    extraction = await asyncio.to_thread(report_parser.extract_text, path, suffix, provider_name)
    raw_text = extraction["raw_text"]
    warnings: list[str] = list(extraction["warnings"])

    # Step 2: detect document type (unless the caller overrode it).
    if document_type_override is not None:
        classification = DocumentClassification(
            document_type=document_type_override, confidence=1.0, auto_detected=False
        )
    else:
        classification = document_classifier.classify(raw_text, filename)
        if classification.document_type == DocumentType.UNKNOWN:
            warnings.append(
                "Could not confidently auto-detect the document type. "
                "Results below use best-effort generic parsing."
            )

    document_type = classification.document_type

    # Step 4: parse structured data.
    lab_analysis = None
    if document_type in LAB_DOCUMENT_TYPES:
        lab_analysis = lab_report_analyzer.analyze(raw_text)
        if lab_analysis.total_count == 0:
            warnings.append("No structured test rows could be detected in this report.")
        fields = DocumentFields()
    else:
        fields = report_parser.parse_structured_sections(raw_text, document_type)

    # Steps 5-8: RAG retrieval, clinical summary, abnormal-finding highlighting,
    # AI explanation — all handled inside clinical_summary.generate_summary.
    summary = await clinical_summary.generate_summary(document_type, fields, lab_analysis, raw_text)

    if lab_analysis and lab_analysis.total_count:
        # Confidence reflects how many detected rows resolved against a
        # reference range (not whether they're abnormal).
        resolved = sum(1 for r in lab_analysis.results if r.ref_low is not None)
        overall_confidence = round(resolved / lab_analysis.total_count, 3)
    else:
        overall_confidence = 0.6 if raw_text.strip() else 0.0
    if not raw_text.strip():
        warnings.append("No text could be extracted from this document.")

    processing_time = time.perf_counter() - started

    return DocumentAnalysisResult(
        filename=filename,
        document_type=document_type,
        classification=classification,
        raw_text=raw_text,
        fields=fields,
        lab_analysis=lab_analysis,
        clinical_summary=summary,
        warnings=warnings,
        overall_confidence=overall_confidence,
        processing_time=round(processing_time, 3),
        has_image=False,
    )


# ---------------------------------------------------------------------------
# Persistence — write path
# ---------------------------------------------------------------------------
def _persist_file(src_path: str, record_id: str) -> str | None:
    """Copy the analyzed file into the document store. Returns the dest path."""
    try:
        suffix = Path(src_path).suffix.lower() or ".bin"
        dest = Path(settings.DOCUMENT_INTELLIGENCE_IMAGE_DIR) / f"{record_id}{suffix}"
        shutil.copyfile(src_path, dest)
        return str(dest)
    except Exception:  # noqa: BLE001 — file retention is best-effort
        logger.exception("Failed to persist document file for %s", record_id)
        return None


async def save_document_record(
    file_src: str | None,
    filename: str | None,
    *,
    result: DocumentAnalysisResult | None = None,
    error: str | None = None,
) -> str | None:
    """Persist one document analysis (success or failure). Never raises."""
    try:
        await _ensure_init()
        record_id = uuid.uuid4().hex
        file_path = (
            await asyncio.to_thread(_persist_file, file_src, record_id) if file_src else None
        )

        row: dict[str, Any] = {
            "id": record_id,
            "created_at": utcnow(),
            "filename": filename,
            "file_path": file_path,
            "status": "failed" if error else "success",
            "error": error,
        }
        if result is not None and not error:
            row.update(
                document_type=result.document_type.value,
                classification_confidence=result.classification.confidence,
                raw_text=result.raw_text,
                fields=result.fields.model_dump(mode="json"),
                lab_results=result.lab_analysis.model_dump(mode="json") if result.lab_analysis else {},
                abnormal_count=result.lab_analysis.abnormal_count if result.lab_analysis else 0,
                clinical_summary=result.clinical_summary.model_dump(mode="json"),
                overall_confidence=result.overall_confidence,
                processing_time=result.processing_time,
            )

        async with _Session() as session:
            session.add(DocumentRecord(**row))
            await session.commit()
        logger.info("Saved document record %s (%s)", record_id, row["status"])
        return record_id
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save document record")
        return None


# ---------------------------------------------------------------------------
# Persistence — read path
# ---------------------------------------------------------------------------
def _apply_filters(stmt, *, q, document_type, status, date_from, date_to):
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(DocumentRecord.filename).like(like)
            | func.lower(DocumentRecord.raw_text).like(like)
        )
    if document_type:
        stmt = stmt.where(DocumentRecord.document_type == document_type)
    if status:
        stmt = stmt.where(DocumentRecord.status == status)
    if date_from:
        stmt = stmt.where(DocumentRecord.created_at >= date_from)
    if date_to:
        stmt = stmt.where(DocumentRecord.created_at <= date_to)
    return stmt


async def list_records(
    *,
    q: str | None = None,
    document_type: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """Return a filtered, sorted, paginated page of document history."""
    await _ensure_init()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    filters = dict(q=q, document_type=document_type, status=status, date_from=date_from, date_to=date_to)

    async with _Session() as session:
        total = await session.scalar(
            _apply_filters(select(func.count(DocumentRecord.id)), **filters)
        ) or 0

        order = {
            "oldest": DocumentRecord.created_at.asc(),
            "confidence": DocumentRecord.overall_confidence.desc(),
        }.get(sort, DocumentRecord.created_at.desc())

        stmt = _apply_filters(select(DocumentRecord), **filters).order_by(order)
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
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(DocumentRecord, record_id)
        return row.detail() if row else None


async def get_file_path(record_id: str) -> str | None:
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(DocumentRecord, record_id)
        if row and row.file_path and Path(row.file_path).exists():
            return row.file_path
    return None


async def compute_stats() -> dict:
    await _ensure_init()
    async with _Session() as session:
        total = await session.scalar(select(func.count(DocumentRecord.id))) or 0
        successful = await session.scalar(
            select(func.count(DocumentRecord.id)).where(DocumentRecord.status == "success")
        ) or 0
        avg_conf = await session.scalar(
            select(func.avg(DocumentRecord.overall_confidence)).where(DocumentRecord.status == "success")
        )
        total_abnormal = await session.scalar(select(func.sum(DocumentRecord.abnormal_count))) or 0
        type_rows = await session.execute(
            select(DocumentRecord.document_type, func.count(DocumentRecord.id)).group_by(
                DocumentRecord.document_type
            )
        )
        by_type = {t: c for t, c in type_rows.all()}

    return {
        "total_analyses": int(total),
        "successful_analyses": int(successful),
        "failed_analyses": int(total - successful),
        "by_document_type": by_type,
        "total_abnormal_findings": int(total_abnormal),
        "average_confidence": round(float(avg_conf or 0.0), 3),
    }


# ---------------------------------------------------------------------------
# Delete path
# ---------------------------------------------------------------------------
def _remove_file(file_path: str | None) -> None:
    if file_path:
        try:
            os.remove(file_path)
        except OSError:
            pass


async def delete_record(record_id: str) -> bool:
    await _ensure_init()
    async with _Session() as session:
        row = await session.get(DocumentRecord, record_id)
        if not row:
            return False
        file_path = row.file_path
        await session.delete(row)
        await session.commit()
    await asyncio.to_thread(_remove_file, file_path)
    logger.info("Deleted document record %s", record_id)
    return True


async def clear_records() -> int:
    await _ensure_init()
    async with _Session() as session:
        paths = (await session.scalars(select(DocumentRecord.file_path))).all()
        count = await session.scalar(select(func.count(DocumentRecord.id))) or 0
        await session.execute(delete(DocumentRecord))
        await session.commit()
    for p in paths:
        await asyncio.to_thread(_remove_file, p)
    logger.info("Cleared document history (%d records)", count)
    return int(count)
