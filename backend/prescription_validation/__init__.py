"""Prescription Validation module.

Production-ready, deterministic prescription-safety validation for the Medical
AI Assistant. After OCR extracts the medicines from a prescription, this module
checks them for duplicates, duplicate active ingredients, missing dosing
information, error-prone abbreviations, suspicious/low-confidence names and
composite prescription errors, then scores the prescription 0..100 and grades it
Safe / Needs Review / High Risk with a plain-language reason and fix for every
finding.

Public surface:

* :data:`router`                — FastAPI router (mounted at ``/validation``)
* :func:`validate_prescription` — coroutine for a :class:`ValidationRequest`
* :func:`validate_from_ocr`     — coroutine the OCR flow uses for auto-validation
* :func:`get_service`           — the process-wide validation service

Internal layers (see the individual modules):

* ``rules``      — pure safety knowledge (abbreviations, ingredient map, weights)
* ``validator``  — the deterministic checks + scoring/grading (pure, testable)
* ``service``    — async orchestration + persistence
"""

from backend.prescription_validation.router import router
from backend.prescription_validation.service import (
    get_service,
    validate_from_ocr,
    validate_prescription,
)

__all__ = ["router", "get_service", "validate_from_ocr", "validate_prescription"]
