"""Batch OCR evaluation over a folder of prescription images.

Pipeline per image::

    discover → preprocess (dataset_loader) → existing OCR pipeline
    (EasyOCR/Tesseract ensemble + confidence selection) → RapidFuzz/Jellyfish
    medicine matching → save per-image JSON → aggregate metrics

The heavy OCR work reuses :func:`backend.ocr.pipeline.run_pipeline` verbatim,
so the dataset is scored with the *exact same* engine, matching and medicine
dataset as the live ``/ocr/extract-prescription`` upload endpoint. Nothing in
the existing flow is modified.

Because local handwriting OCR is slow (seconds per image × ~129 images), the
run is executed in a background thread and the frontend polls a job-status
endpoint for live progress. Per-image results are written to
``backend/ocr/results/`` and a combined report to
``backend/ocr/results/evaluation_report_<job_id>.json``.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.config import ROOT_DIR
from backend.ocr import dataset_loader as loader
from backend.ocr.pipeline import run_pipeline
from backend.ocr.schemas import (
    DatasetEvaluationMetrics,
    DatasetEvaluationReport,
    DatasetImageResult,
    EvaluationJobStatus,
)

# Default dataset shipped with this feature; overridable per request.
DEFAULT_DATASET = ROOT_DIR / "datasets" / "prescriptions" / "illegible_dataset"

# Where per-image JSON + the aggregate report are written.
RESULTS_DIR = Path(__file__).resolve().parent / "results"
PROCESSED_DIR = RESULTS_DIR / "processed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------
# Single-image evaluation
# --------------------------------------------------------------------------
def evaluate_image(image_path: Path) -> DatasetImageResult:
    """Run one image through preprocessing + the existing OCR pipeline.

    Always returns a :class:`DatasetImageResult` (never raises) so a single bad
    image cannot abort a whole dataset run.
    """
    _ensure_dirs()
    name = image_path.name
    start = time.perf_counter()
    try:
        # Preprocess once (Resize→Grayscale→Deskew→Denoise→CLAHE→Contrast→
        # Sharpen) and feed the cleaned image straight into the OCR pipeline.
        processed_path = loader.preprocess_to_file(image_path, PROCESSED_DIR)
        result = run_pipeline(processed_path, preprocess=False)

        matched = [m.name for m in result.medicines if m.name]
        elapsed = round(time.perf_counter() - start, 3)

        img_result = DatasetImageResult(
            image=name,
            status="processed",
            best_engine=result.best_engine,
            overall_confidence=result.overall_confidence,
            medicine_count=len(matched),
            medicines=matched,
            raw_text=result.raw_text,
            processing_time=elapsed,
        )

        # Persist the full structured result for this image.
        out_json = RESULTS_DIR / f"{image_path.stem}.json"
        _write_json(
            out_json,
            {
                "image": name,
                "best_engine": result.best_engine,
                "overall_confidence": result.overall_confidence,
                "processing_time": elapsed,
                "medicines": [m.model_dump() for m in result.medicines],
                "fields": result.fields.model_dump(),
                "doctor_notes": result.doctor_notes,
                "raw_text": result.raw_text,
                "warnings": result.warnings,
                "engines": result.engines,
            },
        )
        img_result.result_json = out_json.name
        return img_result
    except Exception as exc:  # noqa: BLE001 - record failure, keep going
        elapsed = round(time.perf_counter() - start, 3)
        return DatasetImageResult(
            image=name,
            status="failed",
            processing_time=elapsed,
            error=str(exc),
        )


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------
def build_metrics(results: list[DatasetImageResult]) -> DatasetEvaluationMetrics:
    """Compute aggregate metrics from per-image results."""
    total = len(results)
    processed = [r for r in results if r.status == "processed"]
    failed = total - len(processed)

    avg_conf = (
        round(sum(r.overall_confidence for r in processed) / len(processed), 4)
        if processed else 0.0
    )
    with_meds = [r for r in processed if r.medicine_count > 0]
    extraction_accuracy = (
        round(len(with_meds) / len(processed), 4) if processed else 0.0
    )
    total_meds = sum(r.medicine_count for r in processed)
    avg_time = (
        round(sum(r.processing_time for r in results) / total, 3) if total else 0.0
    )

    return DatasetEvaluationMetrics(
        total_images=total,
        processed_images=len(processed),
        failed_images=failed,
        average_confidence=avg_conf,
        medicine_extraction_accuracy=extraction_accuracy,
        total_medicines_extracted=total_meds,
        average_processing_time=avg_time,
    )


# --------------------------------------------------------------------------
# Background job manager
# --------------------------------------------------------------------------
@dataclass
class _Job:
    job_id: str
    dataset: str
    images: list[Path]
    status: str = "running"            # running | completed | failed
    processed: int = 0
    failed: int = 0
    current_image: str | None = None
    started_at: str = field(default_factory=_now_iso)
    finished_at: str | None = None
    error: str | None = None
    results: list[DatasetImageResult] = field(default_factory=list)
    report_path: str | None = None
    report: DatasetEvaluationReport | None = None


_JOBS: dict[str, _Job] = {}
_LOCK = threading.Lock()


def _status_from_job(job: _Job) -> EvaluationJobStatus:
    return EvaluationJobStatus(
        job_id=job.job_id,
        status=job.status,
        total=len(job.images),
        processed=job.processed,
        failed=job.failed,
        current_image=job.current_image,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        report=job.report,
    )


def _run_job(job_id: str) -> None:
    """Worker body: evaluate every image, updating progress as it goes."""
    job = _JOBS[job_id]
    try:
        for image_path in job.images:
            with _LOCK:
                job.current_image = image_path.name
            res = evaluate_image(image_path)
            with _LOCK:
                job.results.append(res)
                if res.status == "processed":
                    job.processed += 1
                else:
                    job.failed += 1

        metrics = build_metrics(job.results)
        report = DatasetEvaluationReport(
            dataset=job.dataset,
            generated_at=_now_iso(),
            metrics=metrics,
            results=job.results,
        )
        report_file = RESULTS_DIR / f"evaluation_report_{job_id}.json"
        _write_json(report_file, report.model_dump())

        with _LOCK:
            job.report = report
            job.report_path = str(report_file)
            job.current_image = None
            job.finished_at = _now_iso()
            job.status = "completed"
    except Exception as exc:  # noqa: BLE001
        with _LOCK:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = _now_iso()


def start_evaluation(dataset_dir: str | None = None, limit: int | None = None) -> EvaluationJobStatus:
    """Discover images and launch a background evaluation job.

    Raises ``FileNotFoundError`` if no images are found, so the route can return
    a clean 404 instead of starting an empty job.
    """
    _ensure_dirs()
    dataset_path = Path(dataset_dir) if dataset_dir else DEFAULT_DATASET
    if not dataset_path.is_absolute():
        dataset_path = ROOT_DIR / dataset_path

    images = loader.discover_images(dataset_path)
    if limit is not None and limit > 0:
        images = images[:limit]
    if not images:
        raise FileNotFoundError(f"No images found in dataset: {dataset_path}")

    job_id = uuid.uuid4().hex[:12]
    job = _Job(job_id=job_id, dataset=str(dataset_path), images=images)
    with _LOCK:
        _JOBS[job_id] = job

    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    thread.start()
    return _status_from_job(job)


def get_status(job_id: str) -> EvaluationJobStatus | None:
    job = _JOBS.get(job_id)
    if job is None:
        return None
    with _LOCK:
        return _status_from_job(job)


def get_report_path(job_id: str) -> str | None:
    job = _JOBS.get(job_id)
    return job.report_path if job else None
