"""FastAPI routes for the redesigned prescription OCR system."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.config import settings
from backend.ocr import evaluation
from backend.ocr.dataset_loader import count_images
from backend.ocr.pipeline import run_pipeline
from backend.ocr.providers.factory import resolve_provider_name
from backend.ocr.schemas import EvaluationJobStatus, PrescriptionResult

router = APIRouter(prefix="/ocr", tags=["prescription-ocr"])

_ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


@router.get("/health")
def ocr_health() -> dict:
    """Report which engine will actually be used (after auto-resolution)."""
    active = resolve_provider_name()
    return {
        "configured": settings.OCR_PROVIDER,
        "active_provider": active,
        "is_local": active == "local",
        "preprocessing": settings.ENABLE_PREPROCESSING,
        "match_threshold": settings.MEDICINE_MATCH_THRESHOLD,
    }


@router.post("/extract-prescription", response_model=PrescriptionResult)
async def extract_prescription(
    file: UploadFile = File(...),
    provider: str | None = Query(
        default=None,
        description="Override OCR engine: gemini | openai | google_vision | local",
    ),
) -> PrescriptionResult:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED)}",
        )

    # Save to a unique path so concurrent uploads never collide.
    dest = Path(settings.UPLOAD_DIR) / f"{uuid.uuid4().hex}{suffix}"
    try:
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    try:
        return run_pipeline(str(dest), provider_name=provider)
    except RuntimeError as exc:
        # Misconfiguration (missing key / SDK) -> actionable 503.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc
    finally:
        dest.unlink(missing_ok=True)  # don't retain medical images on disk


# =========================================================================
# Dataset evaluation (batch OCR over the handwritten-prescription dataset)
# =========================================================================
@router.post("/evaluate-dataset", response_model=EvaluationJobStatus)
def evaluate_dataset(
    dataset: str | None = Query(
        default=None,
        description="Dataset directory (absolute, or relative to the repo root). "
        "Defaults to datasets/prescriptions/illegible_dataset/.",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        description="Optional cap on the number of images to evaluate (for a quick run).",
    ),
) -> EvaluationJobStatus:
    """Kick off a background evaluation of the whole dataset.

    Returns immediately with a ``job_id``; poll ``/ocr/evaluate-dataset/status/{job_id}``
    for live progress and the final report.
    """
    try:
        return evaluation.start_evaluation(dataset_dir=dataset, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluate-dataset/status/{job_id}", response_model=EvaluationJobStatus)
def evaluate_dataset_status(job_id: str) -> EvaluationJobStatus:
    """Poll the live status (and final report) of an evaluation job."""
    status = evaluation.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
    return status


@router.get("/evaluate-dataset/report/{job_id}")
def evaluate_dataset_report(job_id: str) -> FileResponse:
    """Download the saved JSON evaluation report for a completed job."""
    report_path = evaluation.get_report_path(job_id)
    if not report_path or not Path(report_path).exists():
        raise HTTPException(
            status_code=404,
            detail="Report not ready. The job may still be running or may not exist.",
        )
    return FileResponse(
        report_path,
        media_type="application/json",
        filename=f"evaluation_report_{job_id}.json",
    )


@router.get("/dataset-info")
def dataset_info(dataset: str | None = Query(default=None)) -> dict:
    """Report how many images the dataset contains (for the UI before running)."""
    from backend.config import ROOT_DIR

    path = Path(dataset) if dataset else evaluation.DEFAULT_DATASET
    if not path.is_absolute():
        path = ROOT_DIR / path
    return {"dataset": str(path), "image_count": count_images(path), "exists": path.exists()}
