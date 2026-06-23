"""Orchestrates the prescription OCR pipeline.

preprocess -> recognize -> medicine intelligence -> field extraction ->
structured parsing -> confidence + needs-review flags.

Recognition uses a cloud vision provider when one is configured (auto), and
otherwise the local **multi-engine ensemble** (EasyOCR / PaddleOCR / DocTR /
TrOCR / Tesseract) which scores candidates and picks the best.
"""

from __future__ import annotations

from backend.config import settings
from backend.ocr import field_extraction as fe
from backend.ocr import parser as rx_parser
from backend.ocr.engines.ensemble import run_ensemble
from backend.ocr.medicine_intelligence import get_index
from backend.ocr.preprocess import prepare_for_deep_model
from backend.ocr.providers.base import OCRSegment, RawOCRResult
from backend.ocr.providers.factory import get_provider, resolve_provider_name
from backend.ocr.schemas import (
    ExtractedMedicine,
    MedicineCandidate,
    MedicineDetails,
    PrescriptionFields,
    PrescriptionResult,
)


def _looks_like_noise(text: str) -> bool:
    return sum(c.isalpha() for c in text) < 3


def _row_confidence(match_score: float, seg_conf: float | None) -> float:
    dict_conf = match_score / 100.0
    if seg_conf is None:
        return round(dict_conf, 3)
    return round(0.7 * dict_conf + 0.3 * seg_conf, 3)


def _process_segment(seg: OCRSegment) -> ExtractedMedicine | None:
    index = get_index()
    query = (seg.medicine_hint or seg.text).strip()
    if _looks_like_noise(query):
        return None

    matches = index.search(query, limit=3)
    candidates = [MedicineCandidate(name=m.name, score=m.score) for m in matches]
    best = matches[0] if matches else None

    parsed = fe.extract_fields(seg.text)
    dosage = seg.dosage_hint or parsed["dosage"]
    freq_raw = seg.frequency_hint or parsed["frequency"]
    _, freq_expanded = fe.extract_frequency(freq_raw or "")
    freq_expanded = freq_expanded or parsed["frequency_expanded"]
    duration = seg.duration_hint or parsed["duration"]

    match_score = best.score if best else 0.0
    confidence = _row_confidence(match_score, seg.confidence)
    needs_review = match_score < settings.MEDICINE_MATCH_THRESHOLD

    details = None
    name = None
    if best and not needs_review:
        name = best.name
        details = MedicineDetails(**index.details(best.name))

    return ExtractedMedicine(
        raw_text=seg.text,
        name=name,
        candidates=candidates,
        dosage=dosage or None,
        frequency=freq_raw or None,
        frequency_expanded=freq_expanded or None,
        duration=duration or None,
        confidence=confidence,
        needs_review=needs_review,
        details=details,
    )


def _recognize(image_path: str, provider_name: str | None):
    """Return (RawOCRResult, engine_table, best_engine_name)."""
    resolved = resolve_provider_name(provider_name)
    # Cloud providers (when a key is configured) — single best engine.
    if resolved in {"gemini", "openai", "google_vision"}:
        try:
            provider = get_provider(provider_name)
            return provider.extract(image_path), {}, provider.name
        except Exception:  # noqa: BLE001 — fall through to local ensemble
            pass

    # Local multi-engine ensemble.
    index = get_index()
    best, table = run_ensemble(image_path, index)
    raw = RawOCRResult(
        provider=f"ensemble:{best.engine}",
        full_text=best.text,
        segments=[OCRSegment(text=l.text, confidence=l.confidence) for l in best.lines],
    )
    return raw, table, best.engine


def run_pipeline(
    image_path: str,
    provider_name: str | None = None,
    preprocess: bool = True,
) -> PrescriptionResult:
    # 1. Preprocess. Callers that have already cleaned the image (e.g. the
    #    dataset evaluator) pass ``preprocess=False`` to avoid doing it twice.
    processed = (
        prepare_for_deep_model(image_path, settings.UPLOAD_DIR)
        if preprocess and settings.ENABLE_PREPROCESSING
        else image_path
    )

    # 2. Recognize (cloud provider or local ensemble).
    raw, engine_table, best_engine = _recognize(processed, provider_name)

    # 3 + 4. Medicine intelligence + field extraction per line.
    medicines: list[ExtractedMedicine] = []
    for seg in raw.segments:
        item = _process_segment(seg)
        if item is not None:
            medicines.append(item)

    deduped: dict[str, ExtractedMedicine] = {}
    passthrough: list[ExtractedMedicine] = []
    for m in medicines:
        if m.name:
            if m.name not in deduped or m.confidence > deduped[m.name].confidence:
                deduped[m.name] = m
        else:
            passthrough.append(m)
    final = list(deduped.values()) + passthrough

    # 5. Structured fields (doctor/patient/vitals/...).
    fields = PrescriptionFields(**rx_parser.parse_fields(raw.full_text))

    # 6. Confidence + warnings.
    confident = [m for m in final if not m.needs_review]
    overall = (
        round(sum(m.confidence for m in confident) / len(confident), 3)
        if confident else 0.0
    )
    warnings: list[str] = []
    if not final:
        warnings.append("No medicines could be read. Try a clearer photo.")
    if overall and overall < settings.MIN_CONFIDENCE:
        warnings.append("Low overall confidence — please verify every item manually.")
    review_count = sum(1 for m in final if m.needs_review)
    if review_count:
        warnings.append(f"{review_count} item(s) need manual verification.")

    return PrescriptionResult(
        provider=raw.provider,
        medicines=final,
        fields=fields,
        doctor_notes=raw.notes,
        raw_text=raw.full_text,
        overall_confidence=overall,
        warnings=warnings,
        engines=engine_table,
        best_engine=best_engine,
    )
