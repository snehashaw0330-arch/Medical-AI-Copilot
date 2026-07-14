"""Automatic document-type detection (step 2 of the workflow).

Pure keyword-scoring over the OCR'd/extracted text — no model, no external
call, so it is instant and always available (offline-safe, same philosophy as
the rest of the codebase). Callers may bypass this entirely by passing an
explicit ``document_type`` to :func:`backend.document_intelligence.service.analyze_document`.
"""

from __future__ import annotations

import re

from backend.document_intelligence.schemas import DocumentClassification, DocumentType

# Keyword lists are lowercase; matching is substring-based against lowercased
# text. Order matters only for the generic BLOOD_TEST_REPORT fallback, which
# is scored last so a more specific panel (CBC/LFT/KFT/Lipid/Thyroid) wins
# when its keywords are also present.
_KEYWORDS: dict[DocumentType, list[str]] = {
    DocumentType.CBC_REPORT: [
        "complete blood count", "cbc", "hemoglobin", "haemoglobin", "wbc count",
        "rbc count", "platelet count", "hematocrit", "haematocrit", "mcv", "mch",
        "mchc", "total leucocyte count", "tlc", "differential count", "neutrophils",
        "lymphocytes", "eosinophils", "basophils", "monocytes",
    ],
    DocumentType.LFT_REPORT: [
        "liver function test", "lft", "sgot", "sgpt", "ast", "alt",
        "bilirubin", "alkaline phosphatase", "total protein", "albumin",
        "globulin", "a/g ratio", "ggt", "gamma gt",
    ],
    DocumentType.KFT_REPORT: [
        "kidney function test", "renal function test", "kft", "rft",
        "blood urea", "serum creatinine", "creatinine", "uric acid", "egfr",
        "gfr", "bun", "sodium", "potassium", "chloride",
    ],
    DocumentType.LIPID_PROFILE: [
        "lipid profile", "total cholesterol", "triglycerides", "hdl", "ldl",
        "vldl", "cholesterol/hdl ratio", "cholesterol ratio",
    ],
    DocumentType.THYROID_REPORT: [
        "thyroid function test", "thyroid profile", "tsh", "free t3", "free t4",
        "total t3", "total t4", "triiodothyronine", "thyroxine",
    ],
    DocumentType.DISCHARGE_SUMMARY: [
        "discharge summary", "date of admission", "date of discharge",
        "admission date", "discharge date", "course in hospital",
        "condition at discharge", "discharge medications", "reason for admission",
    ],
    DocumentType.MEDICAL_CERTIFICATE: [
        "medical certificate", "this is to certify", "fit to join", "fit to resume",
        "unfit for duty", "certified that", "certificate of fitness", "sick leave",
        "medical leave",
    ],
    DocumentType.HANDWRITTEN_PRESCRIPTION: [
        "rx", "tab.", "tablet", "cap.", "capsule", "syrup", "od", "bd", "tds",
        "mg", "dosage", "prescribed", "take after food", "take before food",
    ],
    DocumentType.BLOOD_TEST_REPORT: [
        "test name", "reference range", "reference interval", "normal range",
        "lab report", "laboratory report", "specimen", "pathology report",
        "investigation report",
    ],
}

# A minimum score below which we don't trust any specific classification.
_MIN_CONFIDENT_MATCHES = 1


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def classify(raw_text: str, filename: str | None = None) -> DocumentClassification:
    """Score ``raw_text`` (+ optionally ``filename``) against every known type.

    Returns the best-scoring :class:`DocumentType` with a 0..1 confidence
    (matches / keywords-checked, capped) and the keywords that matched. Falls
    back to ``UNKNOWN`` when nothing scores above the confidence floor.
    """
    haystack = _normalize(f"{raw_text}\n{filename or ''}")

    best_type = DocumentType.UNKNOWN
    best_matches: list[str] = []
    best_score = 0

    for doc_type, keywords in _KEYWORDS.items():
        matched = [kw for kw in keywords if kw in haystack]
        score = len(matched)
        if score > best_score:
            best_type, best_matches, best_score = doc_type, matched, score

    if best_score < _MIN_CONFIDENT_MATCHES:
        return DocumentClassification(
            document_type=DocumentType.UNKNOWN,
            confidence=0.0,
            matched_keywords=[],
            auto_detected=True,
        )

    confidence = round(min(best_score / 4.0, 1.0), 3)
    return DocumentClassification(
        document_type=best_type,
        confidence=confidence,
        matched_keywords=best_matches,
        auto_detected=True,
    )
