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
