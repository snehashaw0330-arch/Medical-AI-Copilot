"""FastAPI routes for the Medical Report Generator module (all async).

Endpoints
---------
* ``POST   /reports/generate``      — build + store a report from an OCR result
* ``GET    /reports``               — filtered, paginated list
* ``GET    /reports/stats``         — dashboard aggregates
* ``GET    /reports/{id}``          — full stored report (for the viewer)
* ``GET    /reports/{id}/image``    — the retained prescription image
* ``GET    /reports/{id}/pdf``      — download the PDF export
* ``GET    /reports/{id}/html``     — download the HTML export
* ``GET    /reports/{id}/json``     — download the JSON export
* ``DELETE /reports/{id}``          — delete one report (and its image)
* ``DELETE /reports``               — clear all reports

Static sub-paths (``/generate``, ``/stats``) are declared before the dynamic
``/{report_id}`` route so they match first. Every handler logs and turns failures
into actionable HTTP errors — a report problem never crashes the app.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response

from backend.report_generator.pdf_generator import reportlab_available
from backend.report_generator.schemas import (
    DeleteResult,
    ReportDetail,
    ReportGenerateRequest,
    ReportPage,
    ReportStats,
)
from backend.report_generator.service import get_service

logger = logging.getLogger("report_generator")

router = APIRouter(prefix="/reports", tags=["medical-reports"])


def _safe_name(report: dict, ext: str) -> str:
    """A friendly download filename derived from the report."""
    base = (report.get("content", {}).get("filename") or report.get("id") or "report")
    base = str(base).rsplit(".", 1)[0]
    return f"medisense-report-{base}.{ext}"


@router.post("/generate", response_model=ReportDetail)
async def generate_report(req: ReportGenerateRequest) -> ReportDetail:
    """Build and (optionally) persist a comprehensive report from an OCR result."""
    try:
        detail = await get_service().generate(req)
        return ReportDetail(**detail)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Report generation failed")
        raise HTTPException(
            status_code=500, detail=f"Report generation failed: {exc}"
        ) from exc


@router.get("", response_model=ReportPage)
async def list_reports(
    q: str | None = Query(None, description="Search filename, patient or medicines"),
    patient: str | None = Query(None, description="Filter by patient name"),
    date_from: datetime | None = Query(None, description="ISO lower bound (inclusive)"),
    date_to: datetime | None = Query(None, description="ISO upper bound (inclusive)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ReportPage:
    """Filtered, paginated list of generated reports (newest first)."""
    try:
        result = await get_service().list_reports(
            q=q, patient=patient, date_from=date_from, date_to=date_to,
            page=page, page_size=page_size,
        )
        return ReportPage(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list reports")
        raise HTTPException(status_code=500, detail=f"Could not load reports: {exc}") from exc


@router.get("/stats", response_model=ReportStats)
async def report_stats() -> ReportStats:
    """Aggregate statistics for the dashboard cards."""
    try:
        return ReportStats(**await get_service().compute_stats())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to compute report stats")
        raise HTTPException(status_code=500, detail=f"Could not load stats: {exc}") from exc


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(report_id: str) -> ReportDetail:
    """Full stored report (powers the Report Viewer)."""
    detail = await get_service().get_report(report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No report: {report_id}")
    return ReportDetail(**detail)


@router.get("/{report_id}/image")
async def get_report_image(report_id: str) -> FileResponse:
    """Serve the retained prescription image for a report."""
    path = await get_service().get_image_path(report_id)
    if not path:
        raise HTTPException(status_code=404, detail="No image stored for this report.")
    return FileResponse(path)


@router.get("/{report_id}/json")
async def download_report_json(report_id: str) -> Response:
    """Download the report as a JSON file."""
    detail = await get_service().export_json(report_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No report: {report_id}")
    payload = json.dumps(detail, default=str, indent=2)
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{_safe_name(detail, "json")}"'},
    )


@router.get("/{report_id}/html")
async def download_report_html(
    report_id: str,
    download: bool = Query(False, description="Force a file download instead of inline view"),
) -> HTMLResponse:
    """View (default) or download a self-contained HTML document for the report."""
    html = await get_service().export_html(report_id)
    if html is None:
        raise HTTPException(status_code=404, detail=f"No report: {report_id}")
    headers = {}
    if download:
        detail = await get_service().get_report(report_id) or {"id": report_id}
        headers["Content-Disposition"] = f'attachment; filename="{_safe_name(detail, "html")}"'
    return HTMLResponse(content=html, headers=headers)


@router.get("/{report_id}/pdf")
async def download_report_pdf(report_id: str) -> Response:
    """Download the report as a PDF."""
    if not reportlab_available():
        # Graceful, actionable failure — JSON/HTML still work.
        raise HTTPException(
            status_code=503,
            detail="PDF export is unavailable: install 'reportlab' "
                   "(pip install reportlab). JSON and HTML export still work.",
        )
    try:
        pdf = await get_service().export_pdf(report_id)
    except RuntimeError as exc:  # reportlab missing at render time
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if pdf is None:
        raise HTTPException(status_code=404, detail=f"No report: {report_id}")
    detail = await get_service().get_report(report_id) or {"id": report_id}
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_safe_name(detail, "pdf")}"'},
    )


@router.delete("/{report_id}", response_model=DeleteResult)
async def delete_report(report_id: str) -> DeleteResult:
    """Delete a single report (and its retained image)."""
    deleted = await get_service().delete_report(report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No report: {report_id}")
    return DeleteResult(deleted=1, message="Report deleted.")


@router.delete("", response_model=DeleteResult)
async def clear_reports() -> DeleteResult:
    """Delete every report (and all retained images)."""
    try:
        count = await get_service().clear_reports()
        return DeleteResult(deleted=count, message=f"Cleared {count} report(s).")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to clear reports")
        raise HTTPException(status_code=500, detail=f"Could not clear reports: {exc}") from exc
