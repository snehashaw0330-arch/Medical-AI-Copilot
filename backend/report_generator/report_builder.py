"""Report assembly — turns a raw OCR result into a structured ``ReportContent``.

Pure functions (no I/O) that normalise a serialised ``PrescriptionResult`` — the
OCR endpoint's response, which already carries the ``drug_interactions`` and
``clinical_report`` sub-reports produced downstream — into the single, typed
:class:`ReportContent` shape the viewer and the PDF/HTML renderers consume.

Keeping this separate from :mod:`service` (persistence) and the renderers means
the *mapping* logic lives in one auditable place and is trivial to unit-test.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.report_generator.schemas import (
    PatientInfo,
    RagDocument,
    ReportContent,
    ReportMedicine,
)


def _f(value: Any, default: float = 0.0) -> float:
    """Best-effort float coercion."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_str(value: Any) -> str | None:
    """Return a stripped string, or None when empty/missing."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _patient_from_fields(fields: dict) -> PatientInfo:
    """Map OCR ``PrescriptionFields`` onto the report's patient section."""
    fields = fields or {}
    return PatientInfo(
        name=_clean_str(fields.get("patient")),
        age=_clean_str(fields.get("age")),
        gender=_clean_str(fields.get("gender")),
        doctor=_clean_str(fields.get("doctor")),
        hospital=_clean_str(fields.get("hospital")),
        date=_clean_str(fields.get("date")),
        diagnosis=_clean_str(fields.get("diagnosis")),
    )


def _medicines_from_ocr(medicines: list[dict]) -> list[ReportMedicine]:
    """Flatten OCR ``ExtractedMedicine`` dicts into ``ReportMedicine`` rows."""
    out: list[ReportMedicine] = []
    for m in medicines or []:
        details = m.get("details") or {}
        # Frequency prefers the human-expanded form when present.
        freq = m.get("frequency_expanded") or m.get("frequency")
        out.append(ReportMedicine(
            name=_clean_str(m.get("name")),
            raw_text=m.get("raw_text", "") or "",
            confidence=_f(m.get("confidence")),
            dosage=_clean_str(m.get("dosage")),
            frequency=_clean_str(freq),
            duration=_clean_str(m.get("duration")),
            needs_review=bool(m.get("needs_review")),
            candidates=(m.get("candidates") or [])[:5],
            uses=(details.get("uses") or [])[:5],
            side_effects=(details.get("side_effects") or [])[:6],
        ))
    return out


def _collect_sources(
    ocr_result: dict, interactions: dict | None, clinical: dict | None
) -> list[str]:
    """Union of every provenance label that fed the report."""
    sources: list[str] = []
    provider = _clean_str(ocr_result.get("provider"))
    if provider:
        sources.append(f"ocr:{provider}")
    if clinical:
        sources.extend(clinical.get("sources", []) or [])
        sources.extend(clinical.get("rag_sources", []) or [])
    if interactions:
        sources.extend(interactions.get("rag_sources", []) or [])
        if interactions.get("interactions"):
            sources.append("drug-interaction-dataset")
    # Order-preserving de-dupe.
    seen: set[str] = set()
    unique: list[str] = []
    for s in sources:
        key = str(s).strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(str(s).strip())
    return unique


def _rag_documents(interactions: dict | None, clinical: dict | None) -> list[RagDocument]:
    """Retained RAG context. The sub-reports carry synthesised notes + sources
    (not raw chunks), so we surface those as provenance documents."""
    docs: list[RagDocument] = []
    if clinical and clinical.get("rag_notes"):
        docs.append(RagDocument(
            source=", ".join(clinical.get("rag_sources", []) or []) or "knowledge-base",
            text=str(clinical["rag_notes"]),
        ))
    if interactions and interactions.get("rag_notes"):
        docs.append(RagDocument(
            source=", ".join(interactions.get("rag_sources", []) or []) or "knowledge-base",
            text=str(interactions["rag_notes"]),
        ))
    return docs


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = str(it).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def build_content(
    ocr_result: dict,
    *,
    filename: str | None = None,
    processing_time: float = 0.0,
    has_image: bool = False,
    generated_at: datetime | None = None,
    timestamp: str = "",
) -> ReportContent:
    """Assemble a full :class:`ReportContent` from a serialised OCR result."""
    ocr_result = ocr_result or {}
    fields = ocr_result.get("fields") or {}
    interactions = ocr_result.get("drug_interactions")
    clinical = ocr_result.get("clinical_report")

    # AI recommendations = clinical next steps + interaction recommendations.
    recommendations: list[str] = []
    warnings: list[str] = list(ocr_result.get("warnings", []) or [])
    contraindications: list[str] = []
    follow_up: list[str] = []
    disease_prediction: list[dict] = []
    if clinical:
        recommendations.extend(clinical.get("recommended_next_steps", []) or [])
        warnings.extend(clinical.get("warnings", []) or [])
        contraindications.extend(clinical.get("contraindications", []) or [])
        follow_up.extend(clinical.get("follow_up", []) or [])
        disease_prediction = clinical.get("disease_prediction", []) or []
    if interactions:
        recommendations.extend(interactions.get("recommendations", []) or [])

    return ReportContent(
        generated_at=generated_at,
        timestamp=timestamp,
        processing_time=round(_f(processing_time), 3),
        provider=_clean_str(ocr_result.get("provider")),
        engine=_clean_str(ocr_result.get("best_engine")),
        filename=_clean_str(filename),
        has_image=has_image,
        patient=_patient_from_fields(fields),
        raw_text=ocr_result.get("raw_text", "") or "",
        medicines=_medicines_from_ocr(ocr_result.get("medicines", [])),
        overall_confidence=_f(ocr_result.get("overall_confidence")),
        disease_prediction=disease_prediction,
        drug_interactions=interactions,
        clinical=clinical,
        recommendations=_dedupe(recommendations),
        warnings=_dedupe(warnings),
        contraindications=_dedupe(contraindications),
        follow_up=_dedupe(follow_up),
        rag_documents=_rag_documents(interactions, clinical),
        sources=_collect_sources(ocr_result, interactions, clinical),
    )


def record_projection(content: ReportContent) -> dict:
    """Denormalised scalar columns for the DB row (search + list + stats)."""
    names = [m.name for m in content.medicines if m.name]
    clinical = content.clinical or {}
    top_disease = None
    if content.disease_prediction:
        top_disease = content.disease_prediction[0].get("disease")
    return {
        "patient_name": content.patient.name,
        "medicine_names": ",".join(n.lower() for n in names),
        "medicine_count": len(names),
        "overall_confidence": round(content.overall_confidence, 4),
        "risk_level": clinical.get("risk_level"),
        "top_disease": top_disease,
    }
