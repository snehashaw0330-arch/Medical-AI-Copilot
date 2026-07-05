"""FastAPI routes for the redesigned prescription OCR system."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.config import settings
from backend.history import save_ocr_record
from backend.ocr import evaluation
from backend.ocr.dataset_loader import count_images
from backend.ocr.image_quality import assess_image_quality
from backend.ocr.pipeline import run_pipeline
from backend.ocr.providers.factory import resolve_provider_name
from backend.ocr.schemas import (
    EvaluationJobStatus,
    ImageQualityReport,
    PrescriptionResult,
)

logger = logging.getLogger("ocr")

router = APIRouter(prefix="/ocr", tags=["prescription-ocr"])

_ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


async def _attach_interactions(result: PrescriptionResult) -> None:
    """Auto-run drug-interaction analysis when >=2 medicines were detected.

    Best-effort and non-fatal by contract: any failure (missing dataset, etc.)
    is logged and swallowed so the OCR response is never blocked or broken. The
    analysis is *not* persisted to interaction history here — it travels inline
    with the OCR result and is already retained in the OCR history record.
    """
    try:
        names = [m.name for m in result.medicines if m.name]
        if len(names) < 2:
            return
        from backend.drug_interactions import analyze_medicines

        report = await analyze_medicines(names, include_rag=True, persist=True)
        result.drug_interactions = report.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — interaction analysis must never break OCR
        logger.exception("Auto drug-interaction analysis failed (OCR unaffected)")


def _int_or_none(value) -> int | None:
    """Best-effort parse of an OCR'd age string ('45', '45 yrs') to an int."""
    if value is None:
        return None
    import re

    match = re.search(r"\d{1,3}", str(value))
    return int(match.group()) if match else None


async def _attach_clinical(result: PrescriptionResult) -> None:
    """Run clinical decision support after OCR (final stage of the pipeline).

    Completes the OCR -> matching -> interactions -> RAG -> CDSS flow. Reuses the
    already-computed ``drug_interactions`` report so nothing is recomputed, and
    feeds in the parsed patient fields (age, gender, diagnosis) for richer rules.

    Best-effort and non-fatal by contract: any failure is logged and swallowed so
    the OCR response is never blocked or broken. Controlled by CLINICAL_AUTO_ON_OCR.
    """
    if not settings.CLINICAL_AUTO_ON_OCR:
        return
    try:
        names = [m.name for m in result.medicines if m.name]
        if not names:
            return
        from backend.clinical_decision import analyze_clinical
        from backend.clinical_decision.schemas import ClinicalAnalysisRequest

        fields = result.fields
        req = ClinicalAnalysisRequest(
            medicines=names,
            age=_int_or_none(fields.age),
            gender=(fields.gender or None),
            diagnosis=(fields.diagnosis or None),
            include_rag=True,
            persist=True,
        )
        report = await analyze_clinical(req, interaction_report=result.drug_interactions)
        result.clinical_report = report.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — CDSS must never break OCR
        logger.exception("Auto clinical decision support failed (OCR unaffected)")


async def _attach_validation(result: PrescriptionResult) -> None:
    """Validate the extracted prescription for safety issues (Requirement 8).

    Runs after the medicines are parsed and grades the prescription for
    duplicates, missing dosing information, unsafe abbreviations, suspicious /
    low-confidence names and composite errors, stamping the report inline.

    Best-effort and non-fatal by contract: any failure is logged and swallowed so
    the OCR response is never blocked or broken. Controlled by
    VALIDATION_AUTO_ON_OCR. Unlike interaction analysis, this runs even for a
    single medicine — a lone incomplete order is still worth flagging.
    """
    if not settings.VALIDATION_AUTO_ON_OCR:
        return
    try:
        from backend.prescription_validation import validate_from_ocr

        report = await validate_from_ocr(
            result.model_dump(mode="json"), persist=True
        )
        result.validation_report = report.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — validation must never break OCR
        logger.exception("Auto prescription validation failed (OCR unaffected)")


async def _attach_recommendations(result: PrescriptionResult) -> None:
    """Retrieve medicine alternatives + drug info after OCR (Requirement 7).

    For each detected medicine, resolves it against the medicine dataset and
    finds generic equivalents, substitute brands and same-class similar medicines,
    enriched with RAG evidence, stamping the report inline.

    Best-effort and non-fatal by contract: any failure is logged and swallowed so
    the OCR response is never blocked or broken. Controlled by
    MEDICINE_REC_AUTO_ON_OCR.
    """
    if not settings.MEDICINE_REC_AUTO_ON_OCR:
        return
    try:
        names = [m.name or m.raw_text for m in result.medicines if (m.name or m.raw_text)]
        if not names:
            return
        from backend.medicine_recommendation import recommend_from_ocr

        report = await recommend_from_ocr(result.model_dump(mode="json"), persist=True)
        result.recommendation_report = report.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — recommendation must never break OCR
        logger.exception("Auto medicine recommendation failed (OCR unaffected)")


async def _attach_report(
    result: PrescriptionResult,
    image_src: str,
    filename: str | None,
    processing_time: float,
) -> None:
    """Generate + persist a comprehensive medical report after OCR (Requirement 9).

    Runs last in the pipeline, once interactions and the clinical report are
    attached, so the generated report captures the full picture. Retains a copy
    of the prescription image (``image_src`` is still on disk at this point) and
    stamps the new report id back onto the OCR result.

    Best-effort and non-fatal by contract: any failure is logged and swallowed so
    the OCR response is never blocked or broken. Controlled by REPORTS_AUTO_ON_OCR.
    """
    if not settings.REPORTS_AUTO_ON_OCR:
        return
    try:
        from backend.report_generator import generate_from_ocr

        report_id = await generate_from_ocr(
            result.model_dump(mode="json"),
            filename=filename,
            processing_time=processing_time,
            image_src=image_src,
        )
        result.report_id = report_id
    except Exception:  # noqa: BLE001 — report generation must never break OCR
        logger.exception("Auto medical-report generation failed (OCR unaffected)")


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


@router.post("/image-quality", response_model=ImageQualityReport)
async def image_quality(file: UploadFile = File(...)) -> ImageQualityReport:
    """Assess prescription-photo quality *before* OCR.

    Returns a 0..100 overall score, per-metric measurements (blur, brightness,
    contrast, sharpness, noise, resolution, rotation, skew) and actionable
    recommendations. ``passed`` is False when the score is below the warn
    threshold so the UI can prompt the user to recapture before OCR runs.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED)}",
        )

    dest = Path(settings.UPLOAD_DIR) / f"{uuid.uuid4().hex}{suffix}"
    try:
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    try:
        report = assess_image_quality(str(dest))
        return ImageQualityReport(**report.__dict__)
    except ValueError as exc:
        # Unreadable / corrupt image -> actionable 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Image quality assessment failed: {exc}"
        ) from exc
    finally:
        dest.unlink(missing_ok=True)  # don't retain medical images on disk


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

    started = time.perf_counter()

    async def _record(*, result=None, error=None) -> None:
        # Persist every analysis (success or failure) to the OCR history store.
        # Best-effort by contract — save_ocr_record never raises — so history
        # can never break the OCR response.
        await save_ocr_record(
            str(dest),
            file.filename,
            result=result,
            processing_time=time.perf_counter() - started,
            error=error,
        )

    try:
        result = run_pipeline(str(dest), provider_name=provider)
        # Automatically analyse drug interactions when multiple medicines are
        # detected, then run clinical decision support (reusing that report),
        # before persisting so the OCR history captures both inline.
        await _attach_interactions(result)
        await _attach_clinical(result)
        # Validate the prescription for safety issues (duplicates, missing dosing
        # info, unsafe abbreviations, ...) before report generation so the
        # generated report captures it too.
        await _attach_validation(result)
        # Retrieve medicine alternatives + drug information for each detected
        # medicine (generic equivalents, substitute brands, similar medicines).
        await _attach_recommendations(result)
        # Generate a comprehensive medical report (retains the image, which is
        # still on disk here) and stamp its id onto the result before persisting.
        await _attach_report(
            result, str(dest), file.filename, time.perf_counter() - started
        )
        await _record(result=result)
        return result
    except RuntimeError as exc:
        # Misconfiguration (missing key / SDK) -> actionable 503.
        await _record(error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await _record(error=str(exc))
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
