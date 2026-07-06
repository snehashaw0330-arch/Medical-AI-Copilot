"""Health-score engine — the overall 0..100 wellbeing score and its factors.

Pure and deterministic. It consumes a chronological list of *encounters* (one per
report/analysis, oldest→newest; see ``service._to_encounter`` for the shape) and
produces:

* a per-encounter score series (for the Health-Score-Timeline chart), and
* the latest overall score with its six-factor breakdown.

The six factors mirror the requirement: medicine adherence, risk level, disease
progression, drug interactions, prediction confidence and clinical warnings.
Adherence is a documented *proxy* (regimen continuity across visits) since the
platform has no dispensing/consumption feed — it is never presented as measured.
"""

from __future__ import annotations

from typing import Any

# Factor weights (sum to 1.0). Tunable in one place.
WEIGHTS: dict[str, float] = {
    "adherence": 0.20,
    "risk": 0.25,
    "disease_progression": 0.15,
    "drug_interactions": 0.15,
    "prediction_confidence": 0.10,
    "clinical_warnings": 0.15,
}

# risk_level (clinical vocabulary) → wellbeing sub-score (higher = healthier).
_RISK_SUBSCORE = {"low": 90.0, "moderate": 65.0, "medium": 65.0, "high": 40.0,
                  "critical": 15.0, "none": 85.0, None: 80.0, "": 80.0}
# interaction overall_risk → wellbeing sub-score.
_INTERACTION_SUBSCORE = {"none": 95.0, "low": 80.0, "moderate": 55.0, "medium": 55.0,
                         "high": 35.0, "critical": 15.0, None: 85.0, "": 85.0}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def factor_scores(enc: dict, prev: dict | None) -> dict[str, float]:
    """The six 0..100 factor sub-scores for one encounter (higher = healthier)."""
    risk_level = (enc.get("risk_level") or "").lower()
    interaction_risk = (enc.get("interaction_risk") or "none").lower()

    # Adherence proxy: regimen continuity vs the previous visit.
    if prev is None:
        adherence = 72.0
    else:
        prev_meds = set(prev.get("medicine_names", []))
        cur_meds = set(enc.get("medicine_names", []))
        if not prev_meds:
            adherence = 72.0
        else:
            continuity = len(prev_meds & cur_meds) / len(prev_meds)
            adherence = 50.0 + continuity * 45.0

    risk = _RISK_SUBSCORE.get(risk_level, 80.0)
    interactions = _INTERACTION_SUBSCORE.get(interaction_risk, 85.0)

    # Disease progression (instantaneous burden): inverse of the clinical risk score.
    risk_score = enc.get("risk_score")
    if isinstance(risk_score, (int, float)) and risk_score > 0:
        disease_progression = _clamp(100.0 - float(risk_score))
    else:
        disease_progression = risk  # fall back to the risk-level sub-score

    prediction_confidence = _clamp(float(enc.get("overall_confidence") or 0.0) * 100.0)

    warn_count = len(enc.get("warnings", []) or []) + len(enc.get("red_flags", []) or [])
    clinical_warnings = _clamp(100.0 - min(70.0, warn_count * 12.0))

    return {
        "adherence": round(_clamp(adherence), 1),
        "risk": round(risk, 1),
        "disease_progression": round(disease_progression, 1),
        "drug_interactions": round(interactions, 1),
        "prediction_confidence": round(prediction_confidence, 1),
        "clinical_warnings": round(clinical_warnings, 1),
    }


def score_from_factors(factors: dict[str, float]) -> float:
    """Weighted overall score from the six factors."""
    total = sum(factors[k] * WEIGHTS[k] for k in WEIGHTS)
    return round(_clamp(total), 1)


def compute(encounters: list[dict]) -> dict[str, Any]:
    """Return the score series + the latest score and its factor breakdown."""
    if not encounters:
        return {"score": 0.0, "series": [], "breakdown": {**{k: 0.0 for k in WEIGHTS}, "weights": WEIGHTS}}

    series: list[tuple] = []
    latest_factors: dict[str, float] = {}
    for i, enc in enumerate(encounters):
        prev = encounters[i - 1] if i > 0 else None
        factors = factor_scores(enc, prev)
        latest_factors = factors
        series.append((enc["created_at"], score_from_factors(factors)))

    return {
        "score": series[-1][1],
        "series": series,
        "breakdown": {**latest_factors, "weights": WEIGHTS},
    }
