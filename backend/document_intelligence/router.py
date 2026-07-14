"""FastAPI routes for the Medical Document Intelligence module (all async).

Endpoints
---------
* ``POST   /documents/analyze``       — run the full workflow on an uploaded file
* ``GET    /documents/history``       — filtered, paginated list
* ``GET    /documents/stats``         — dashboard aggregates
* ``GET    /documents/{id}``          — full stored record (for the viewer)
* ``GET    /documents/{id}/image``    — the retained original file
* ``GET    /documents/{id}/json``     — download the structured report
* ``DELETE /documents/{id}``          — delete one record (and its file)
* ``DELETE /documents``               — clear all records

Static sub-paths (``/analyze``, ``/history``, ``/stats``) are declared before
the dynamic ``/{record_id}`` route so they are matched first. Every handler
logs and turns failures into actionable HTTP errors — a document-intelligence
problem never crashes the app.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from backend.config import settings
from backend.document_intelligence import service
from backend.document_intelligence.schemas import (
    DeleteResult,
    DocumentAnalysisResult,
    DocumentHistoryDetail,
    DocumentHistoryPage,
    DocumentStats,
    DocumentType,
)

logger = logging.getLogger("document_intelligence")

router = APIRouter(prefix="/documents", tags=["document-intelligence"])

_ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".pdf"}


def _safe_name(record: dict) -> str:
    base = (record.get("filename") or record.get("id") or "document")
    base = str(base).rsplit(".", 1)[0]
    return f"medisense-document-{base}.json"


@router.post("/analyze", response_model=DocumentAnalysisResult)
async def analyze_document(
    file: UploadFile = File(...),
    document_type: str | None = Query(
        default=None,
        description="Override auto-detection with one of the known document types.",
    ),
    provider: str | None = Query(
        default=None,
        description="Override OCR engine for image/scanned-PDF pages: gemini | openai | google_vision | local",
    ),
) -> DocumentAnalysisResult:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED)}",
        )

    override: DocumentType | None = None
    if document_type:
        try:
            override = DocumentType(document_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown document_type '{document_type}'. "
                f"Valid values: {[t.value for t in DocumentType]}",
            ) from exc

    dest = Path(settings.UPLOAD_DIR) / f"{uuid.uuid4().hex}{suffix}"
    try:
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    try:
        result = await service.analyze_document(
            str(dest), file.filename, document_type_override=override, provider_name=provider
        )
        record_id = await service.save_document_record(str(dest), file.filename, result=result)
        result.id = record_id
        result.has_image = record_id is not None
        return result
    except RuntimeError as exc:
        # Misconfiguration (missing OCR key/SDK, etc.) -> actionable 503.
        await service.save_document_record(None, file.filename, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Document analysis failed")
        await service.save_document_record(None, file.filename, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Document analysis failed: {exc}") from exc
    finally:
        dest.unlink(missing_ok=True)  # don't retain raw uploads on disk


@router.get("/history", response_model=DocumentHistoryPage)
async def list_history(
    q: str | None = Query(None, description="Search filename or extracted text"),
    document_type: str | None = Query(None, description="Filter by document type"),
    status: str | None = Query(None, pattern="^(success|failed)$"),
    date_from: datetime | None = Query(None, description="ISO date/time lower bound (inclusive)"),
    date_to: datetime | None = Query(None, description="ISO date/time upper bound (inclusive)"),
    sort: str = Query("newest", pattern="^(newest|oldest|confidence)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> DocumentHistoryPage:
    """Paginated, filterable, sortable list of past document analyses."""
    try:
        result = await service.list_records(
            q=q, document_type=document_type, status=status,
            date_from=date_from, date_to=date_to,
            sort=sort, page=page, page_size=page_size,
        )
        return DocumentHistoryPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list document history")
        raise HTTPException(status_code=500, detail=f"Could not load history: {exc}") from exc


@router.get("/stats", response_model=DocumentStats)
async def document_stats() -> DocumentStats:
    """Aggregate statistics for the dashboard cards."""
    try:
        return DocumentStats(**await service.compute_stats())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute document stats")
        raise HTTPException(status_code=500, detail=f"Could not load stats: {exc}") from exc


@router.get("/{record_id}", response_model=DocumentHistoryDetail)
async def get_document(record_id: str) -> DocumentHistoryDetail:
    """Full detail for one record (raw text, fields, lab analysis, summary)."""
    record = await service.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No document record: {record_id}")
    return DocumentHistoryDetail(**record)


@router.get("/{record_id}/image")
async def get_document_image(record_id: str) -> FileResponse:
    """Serve the retained original file (image or PDF) for a record."""
    path = await service.get_file_path(record_id)
    if not path:
        raise HTTPException(status_code=404, detail="No file stored for this record.")
    return FileResponse(path)


@router.get("/{record_id}/json")
async def download_document_json(record_id: str) -> Response:
    """Download the structured document report as a JSON file."""
    record = await service.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No document record: {record_id}")
    payload = json.dumps(record, default=str, indent=2)
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{_safe_name(record)}"'},
    )


@router.delete("/{record_id}", response_model=DeleteResult)
async def delete_document(record_id: str) -> DeleteResult:
    """Delete a single document record (and its retained file)."""
    deleted = await service.delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No document record: {record_id}")
    return DeleteResult(deleted=1, message="Record deleted.")


@router.delete("", response_model=DeleteResult)
async def clear_documents() -> DeleteResult:
    """Delete every document record (and all retained files)."""
    try:
        count = await service.clear_records()
        return DeleteResult(deleted=count, message=f"Cleared {count} record(s).")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear document history")
        raise HTTPException(status_code=500, detail=f"Could not clear history: {exc}") from exc
