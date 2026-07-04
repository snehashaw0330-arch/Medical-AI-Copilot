"""Pydantic models for the Prescription Validation API (the frontend contract).

These types are the *stable* boundary between the backend validator and the
React UI. A :class:`ValidationReport` is produced by the deterministic rules in
``validator.py`` from the medicines and text an OCR analysis extracted, and is
graded onto a simple, actionable three-level scale.

The scale mirrors the pattern already used by the drug-interaction and clinical
modules so the frontend can reuse the same badge tones:

    safe          → success   (score >= 80, no high-severity issues)
    needs_review  → warning    (medium issues / score 50-79)
    high_risk     → danger     (any high-severity issue / score < 50)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Per-issue severity (drives scoring weight and the risk grade)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    """Three-level prescription-safety grade (Requirement 4)."""

    SAFE = "safe"
    NEEDS_REVIEW = "needs_review"
    HIGH_RISK = "high_risk"


class IssueCategory(str, Enum):
    """The kind of problem a :class:`ValidationIssue` describes."""

    DUPLICATE_MEDICINE = "duplicate_medicine"
    DUPLICATE_INGREDIENT = "duplicate_ingredient"
    MISSING_INFO = "missing_info"
    UNSAFE_ABBREVIATION = "unsafe_abbreviation"
    SUSPICIOUS_NAME = "suspicious_name"
    LOW_CONFIDENCE = "low_confidence"
    PRESCRIPTION_ERROR = "prescription_error"


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class MedicineInput(BaseModel):
    """One medicine to validate.

    Intentionally a permissive subset of the OCR ``ExtractedMedicine`` shape so a
    validation request can be built directly from an OCR result *or* from an
    edited medicine list in the UI. Every field is optional except that a row is
    only meaningful if it carries a ``name`` or ``raw_text``.
    """

    raw_text: str = ""
    name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    frequency_expanded: str | None = None
    duration: str | None = None
    instructions: str | None = None
    confidence: float = 1.0                 # 0..1 for this row
    needs_review: bool = False
    candidates: list[dict[str, Any]] = []   # [{name, score}] from matching
    details: dict[str, Any] | None = None   # MedicineDetails, if resolved


class ValidationRequest(BaseModel):
    """Input for ``POST /validation/check``."""

    medicines: list[MedicineInput] = Field(default_factory=list)
    raw_text: str = ""                       # full OCR text (abbreviation scan)
    fields: dict[str, Any] | None = None     # parsed patient/visit fields
    overall_confidence: float | None = None  # 0..1, from the OCR result
    persist: bool = True                     # save this validation to history
    source_record_id: str | None = None      # optional link to an OCR record


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
class ValidationIssue(BaseModel):
    """A single flagged problem, with a plain-language reason and a fix."""

    code: str                                # stable machine code
    category: IssueCategory
    severity: Severity
    title: str                               # short label for the UI
    detail: str                              # *why* this was flagged
    recommendation: str                      # what to do about it
    medicine: str | None = None              # affected medicine (display name)
    evidence: str | None = None              # matched text / abbreviation


class DuplicateGroup(BaseModel):
    """A set of prescription rows that collapse to the same drug/ingredient."""

    kind: str                                # "medicine" | "active_ingredient"
    value: str                               # the shared name / ingredient
    medicines: list[str] = []                # display names in the group


# --------------------------------------------------------------------------
# Full report
# --------------------------------------------------------------------------
class ValidationReport(BaseModel):
    """Complete prescription-validation report (the frontend contract)."""

    id: str | None = None
    created_at: datetime | None = None

    # --- Headline (Requirements 3 & 4) ------------------------------------
    validation_score: float = 100.0          # 0..100 (higher = safer)
    risk_level: RiskLevel = RiskLevel.SAFE
    summary: str = ""
    medicine_count: int = 0

    # --- All findings + severity tally ------------------------------------
    issues: list[ValidationIssue] = []
    issue_counts: dict[str, int] = {}        # per-severity tally (badges)

    # --- Grouped views the UI renders directly (Requirement 7) ------------
    missing_information: list[ValidationIssue] = []
    duplicate_medicines: list[DuplicateGroup] = []
    warnings: list[ValidationIssue] = []     # abbreviations / suspicious / errors
    suggested_corrections: list[str] = []

    provider: str = "prescription-validator"
    disclaimer: str = (
        "This automated prescription validation is a safety aid only and is NOT "
        "a substitute for review by a licensed pharmacist or physician. Always "
        "verify medicines, dosages and instructions against the original "
        "prescription before dispensing or taking any medication."
    )


# --------------------------------------------------------------------------
# History (list + detail)
# --------------------------------------------------------------------------
class ValidationHistoryItem(BaseModel):
    """Lightweight row for the validation-history list view."""

    id: str
    created_at: datetime
    medicines: list[str] = []
    medicine_count: int = 0
    validation_score: float = 100.0
    risk_level: RiskLevel = RiskLevel.SAFE
    issue_count: int = 0
    summary: str = ""


class ValidationHistoryPage(BaseModel):
    """A page of history items plus pagination metadata."""

    items: list[ValidationHistoryItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
