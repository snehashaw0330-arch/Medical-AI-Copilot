"""Pydantic response models for the OCR API (the frontend contract)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MedicineCandidate(BaseModel):
    name: str
    score: float  # 0..100


class MedicineDetails(BaseModel):
    name: str = ""
    uses: list[str] = []
    side_effects: list[str] = []
    substitutes: list[str] = []
    chemical_class: str = ""
    therapeutic_class: str = ""
    action_class: str = ""
    habit_forming: str = ""


class ExtractedMedicine(BaseModel):
    raw_text: str
    name: str | None = None
    candidates: list[MedicineCandidate] = []
    dosage: str | None = None
    frequency: str | None = None
    frequency_expanded: str | None = None
    duration: str | None = None
    instructions: str | None = None
    confidence: float                    # 0..1 for this row
    needs_review: bool
    details: MedicineDetails | None = None


class PrescriptionFields(BaseModel):
    """Structured non-medicine fields parsed from the prescription."""

    doctor: str | None = None
    hospital: str | None = None
    patient: str | None = None
    age: str | None = None
    gender: str | None = None
    date: str | None = None
    diagnosis: str | None = None
    advice: str | None = None
    follow_up: str | None = None
    investigations: str | None = None
    vitals: dict[str, str] = {}


class PrescriptionResult(BaseModel):
    provider: str                        # engine/provider that produced the text
    medicines: list[ExtractedMedicine] = []
    fields: PrescriptionFields = PrescriptionFields()
    doctor_notes: list[str] = []
    raw_text: str = ""
    overall_confidence: float = 0.0      # 0..1
    warnings: list[str] = []
    engines: dict[str, Any] = {}         # per-engine score table (debug)
    best_engine: str | None = None
    # Auto-populated when >=2 medicines are detected (see ocr/router.py). Optional
    # and defaulted so older clients and non-OCR callers are unaffected.
    drug_interactions: dict[str, Any] | None = None
    # Auto-populated clinical decision-support report (see ocr/router.py). Runs
    # after interactions in the OCR->matching->interactions->RAG->CDSS pipeline.
    # Optional and defaulted so older clients and non-OCR callers are unaffected.
    clinical_report: dict[str, Any] | None = None
    # Id of the medical report auto-generated after OCR (see ocr/router.py). The
    # full report is retrievable at GET /reports/{id}. Optional and defaulted.
    report_id: str | None = None
    # Auto-populated prescription-validation report (see ocr/router.py). Runs
    # after the medicines are extracted and grades the prescription's safety.
    # Optional and defaulted so older clients and non-OCR callers are unaffected.
    validation_report: dict[str, Any] | None = None


# ==========================================================================
# Image quality assessment (runs before OCR)
# ==========================================================================
class ImageQualityMetrics(BaseModel):
    """Raw, per-metric measurements computed with OpenCV."""

    blur_score: float = 0.0        # variance of the Laplacian (higher = sharper)
    brightness: float = 0.0        # mean luminance, 0..255
    contrast: float = 0.0          # std dev of luminance
    sharpness: float = 0.0         # Tenengrad (mean squared Sobel gradient)
    noise_level: float = 0.0       # estimated noise sigma (lower = cleaner)
    width: int = 0
    height: int = 0
    megapixels: float = 0.0
    rotation_angle: float = 0.0    # dominant page rotation, degrees
    skew_angle: float = 0.0        # text-baseline skew, degrees


class ImageQualityReport(BaseModel):
    """Full quality report returned by ``/ocr/image-quality`` (frontend contract)."""

    overall_score: float = 0.0     # 0..100
    rating: str = "Unknown"        # Excellent | Good | Fair | Poor | Unknown
    passed: bool = True            # overall_score >= threshold
    threshold: float = 60.0        # warn the user below this
    metrics: ImageQualityMetrics = ImageQualityMetrics()
    subscores: dict[str, float] = {}   # per-metric 0..100 sub-scores
    recommendations: list[str] = []    # actionable user guidance
    warnings: list[str] = []


# ==========================================================================
# Dataset evaluation (batch OCR over a folder of prescription images)
# ==========================================================================
class DatasetImageResult(BaseModel):
    """Outcome of running one dataset image through the OCR pipeline."""

    image: str                           # file name
    status: str                          # "processed" | "failed"
    best_engine: str | None = None
    overall_confidence: float = 0.0      # 0..1
    medicine_count: int = 0              # confidently matched medicines
    medicines: list[str] = []            # matched medicine names
    raw_text: str = ""
    processing_time: float = 0.0         # seconds
    result_json: str | None = None       # relative path to saved per-image JSON
    error: str | None = None             # populated when status == "failed"


class DatasetEvaluationMetrics(BaseModel):
    """Aggregate metrics across the whole dataset run."""

    total_images: int = 0
    processed_images: int = 0
    failed_images: int = 0
    average_confidence: float = 0.0      # 0..1, over processed images
    # Fraction of processed images from which >=1 medicine was confidently
    # extracted. (This dataset has no transcription ground truth, so accuracy
    # is reported as the confident-extraction rate — documented, not inflated.)
    medicine_extraction_accuracy: float = 0.0   # 0..1
    total_medicines_extracted: int = 0
    average_processing_time: float = 0.0        # seconds per image


class DatasetEvaluationReport(BaseModel):
    """Full evaluation report: metrics + per-image breakdown."""

    dataset: str                         # dataset directory that was evaluated
    generated_at: str                    # ISO timestamp
    metrics: DatasetEvaluationMetrics = DatasetEvaluationMetrics()
    results: list[DatasetImageResult] = []


class EvaluationJobStatus(BaseModel):
    """Live status payload returned while/after an evaluation job runs."""

    job_id: str
    status: str                          # "running" | "completed" | "failed"
    total: int = 0
    processed: int = 0
    failed: int = 0
    current_image: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    report: DatasetEvaluationReport | None = None   # present once completed
