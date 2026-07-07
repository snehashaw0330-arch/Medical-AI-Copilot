"""Confidence analyzer — reliability, calibration, evidence & uncertainty.

A raw confidence number is not enough for a clinical decision. This engine takes
a :class:`DecisionTrace` and derives the richer picture governance requires:

* **Confidence**        — the overall model confidence (0..1).
* **Reliability**       — a band (high/moderate/low/unreliable) and 0..100 score
                          combining confidence, evidence and calibration.
* **Calibration**       — how well the individual stage confidences agree with
                          the overall confidence (low spread ⇒ well-calibrated).
* **Evidence strength** — how much retrieval + matching support the decision.
* **Model uncertainty** — spread of the disease-prediction distribution (a
                          near-tie between top predictions ⇒ high uncertainty).
* **Missing information** — concrete gaps (no dosage, no diagnosis, no evidence…)
                          that a reviewer should close before trusting the output.

Pure and deterministic: identical trace ⇒ identical report.
"""

from __future__ import annotations

from statistics import pstdev

from backend.ai_governance.schemas import (
    ConfidenceReport,
    DecisionStatus,
    DecisionTrace,
    ReliabilityBand,
)


def _pred_score(d: dict) -> float:
    for k in ("probability", "confidence", "score"):
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _evidence_strength(trace: DecisionTrace) -> float:
    """0..1 from RAG retrieval quality + medicine-match coverage."""
    docs = trace.rag_documents
    if docs:
        scores = [min(max(c.score, 0.0), 1.0) if c.score <= 1 else 1.0 for c in docs]
        rag = sum(scores) / len(scores)
        rag *= min(len(docs) / 3.0, 1.0)          # reward having ≥3 documents
    else:
        rag = 0.0
    meds = trace.medicines
    matched = sum(1 for m in meds if m.matched) / len(meds) if meds else 0.0
    return round(min(1.0, 0.6 * rag + 0.4 * matched), 3)


def _calibration(trace: DecisionTrace, overall: float) -> float:
    """1 - normalised spread of the per-stage confidences around the overall."""
    signals = [overall]
    signals += [m.confidence for m in trace.medicines if m.confidence]
    if trace.ocr_confidence:
        signals.append(trace.ocr_confidence)
    preds = [p for p in trace.disease_prediction if isinstance(p, dict)]
    if preds:
        signals.append(_pred_score(preds[0]))
    if len(signals) < 2:
        return 0.75  # not enough signals to judge — neutral-positive default
    spread = pstdev(signals)
    return round(max(0.0, 1.0 - min(spread * 2.0, 1.0)), 3)


def _model_uncertainty(trace: DecisionTrace) -> float:
    """0..1 — a near-tie between the top predictions means high uncertainty."""
    preds = sorted(
        (_pred_score(p) for p in trace.disease_prediction if isinstance(p, dict)),
        reverse=True,
    )
    if not preds:
        # No distribution to judge — fall back to (1 - overall confidence).
        return round(max(0.0, 1.0 - (trace.confidence or 0.0)), 3)
    if len(preds) == 1:
        return round(max(0.0, 1.0 - preds[0]), 3)
    margin = preds[0] - preds[1]
    return round(max(0.0, 1.0 - min(margin * 2.5, 1.0)), 3)


def _missing_information(trace: DecisionTrace) -> list[str]:
    missing: list[str] = []
    if not trace.ocr_text.strip():
        missing.append("No OCR text was extracted from the image.")
    if not trace.medicines:
        missing.append("No medicines were detected to reason about.")
    else:
        if not any(m.dosage for m in trace.medicines):
            missing.append("No dosage information was parsed for any medicine.")
        if any(not m.matched for m in trace.medicines):
            missing.append("One or more medicines could not be matched to the dataset.")
    if not trace.disease_prediction:
        missing.append("No disease prediction was available for this decision.")
    if not trace.rag_documents:
        missing.append("No knowledge-base evidence was retrieved to ground the recommendation.")
    if not trace.final_recommendation:
        missing.append("No final recommendation was produced.")
    return missing


def _band(score: float) -> ReliabilityBand:
    if score >= 78:
        return ReliabilityBand.HIGH
    if score >= 58:
        return ReliabilityBand.MODERATE
    if score >= 38:
        return ReliabilityBand.LOW
    return ReliabilityBand.UNRELIABLE


def analyze(trace: DecisionTrace) -> ConfidenceReport:
    """Full confidence analysis for one decision trace."""
    overall = float(trace.confidence or 0.0)
    evidence = _evidence_strength(trace)
    calibration = _calibration(trace, overall)
    uncertainty = _model_uncertainty(trace)
    missing = _missing_information(trace)

    # Reliability blends confidence, evidence and calibration, then is penalised
    # by model uncertainty and outstanding missing information.
    base = 100.0 * (0.45 * overall + 0.30 * evidence + 0.25 * calibration)
    base *= (1.0 - 0.35 * uncertainty)
    base -= min(len(missing) * 4.0, 20.0)
    if trace.status in (DecisionStatus.FAILED, DecisionStatus.LOW_CONFIDENCE):
        base *= 0.7
    reliability_score = round(max(0.0, min(100.0, base)), 1)
    band = _band(reliability_score)

    drivers: list[str] = []
    drivers.append(f"Overall model confidence is {overall * 100:.0f}%.")
    drivers.append(
        "Evidence support is "
        + ("strong" if evidence >= 0.66 else "moderate" if evidence >= 0.33 else "weak")
        + f" ({evidence * 100:.0f}%)."
    )
    drivers.append(
        "Stage confidences are "
        + ("well-calibrated" if calibration >= 0.66 else
           "loosely calibrated" if calibration >= 0.4 else "poorly calibrated")
        + f" ({calibration * 100:.0f}%)."
    )
    if uncertainty >= 0.5:
        drivers.append(f"Model uncertainty is high ({uncertainty * 100:.0f}%) — competing predictions were close.")
    if missing:
        drivers.append(f"{len(missing)} information gap(s) reduce reliability.")

    summary = (
        f"This decision is {band.value} reliability ({reliability_score:.0f}/100). "
        + ("It is well supported by evidence and consistent across stages."
           if band in (ReliabilityBand.HIGH, ReliabilityBand.MODERATE)
           else "Treat the output with caution and verify against the source prescription.")
    )

    return ConfidenceReport(
        trace_id=trace.trace_id,
        confidence=round(overall, 3),
        reliability=band,
        reliability_score=reliability_score,
        calibration=calibration,
        evidence_strength=evidence,
        model_uncertainty=uncertainty,
        missing_information=missing,
        drivers=drivers,
        summary=summary,
    )
