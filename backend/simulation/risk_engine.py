"""Risk scoring for the Simulation Engine (pure).

Two related jobs, both deterministic:

* :func:`disease_risk` — turns the disease-prediction hypotheses into a graded
  :class:`DiseaseRisk`, amplified by the patient's risk-modifying factors
  (age, pregnancy, renal/hepatic impairment).
* :func:`composite_risk` — rolls the drug interactions, contraindications and
  patient factors into one 0-100 **composite risk score** (lower is safer) plus a
  :class:`RiskLevel`. This is the number the scenario comparison is built on, so a
  clinician can see whether a change made things safer or riskier.
"""

from __future__ import annotations

from backend.simulation.patient_model import PatientFlags
from backend.simulation.schemas import (
    Contraindication,
    DiseaseHypothesis,
    DiseaseRisk,
    RiskLevel,
)

_SEVERITY_WEIGHT = {
    RiskLevel.CRITICAL: 40.0, RiskLevel.HIGH: 25.0,
    RiskLevel.MODERATE: 12.0, RiskLevel.LOW: 4.0,
}
_LEVEL_FROM_SCORE = [
    (75.0, RiskLevel.CRITICAL), (50.0, RiskLevel.HIGH),
    (25.0, RiskLevel.MODERATE), (0.0, RiskLevel.LOW),
]


def _level_from_score(score: float) -> RiskLevel:
    for threshold, level in _LEVEL_FROM_SCORE:
        if score >= threshold:
            return level
    return RiskLevel.LOW


def _interaction_severity(raw: str) -> RiskLevel:
    return {
        "critical": RiskLevel.CRITICAL, "high": RiskLevel.HIGH,
        "moderate": RiskLevel.MODERATE, "low": RiskLevel.LOW,
    }.get(str(raw).lower(), RiskLevel.MODERATE)


def disease_risk(
    hypotheses: list[DiseaseHypothesis], flags: PatientFlags
) -> DiseaseRisk:
    """Grade disease risk from the hypotheses, amplified by patient factors."""
    if not hypotheses:
        base = 0.0
    else:
        # Base severity ≈ leading hypothesis probability (0..100).
        base = min(100.0, hypotheses[0].confidence)

    modifiers: list[str] = []
    amp = 0.0
    if flags.is_geriatric:
        amp += 8.0; modifiers.append("age ≥ 65 raises baseline risk")
    if flags.is_paediatric:
        amp += 6.0; modifiers.append("paediatric physiology")
    if flags.is_pregnant:
        amp += 10.0; modifiers.append("pregnancy")
    if flags.renal_severe:
        amp += 12.0; modifiers.append("severe renal impairment")
    elif flags.renal_impaired:
        amp += 6.0; modifiers.append("renal impairment")
    if flags.hepatic_severe:
        amp += 12.0; modifiers.append("severe hepatic impairment")
    elif flags.hepatic_impaired:
        amp += 6.0; modifiers.append("hepatic impairment")

    score = min(100.0, base + amp) if hypotheses else min(100.0, amp)
    return DiseaseRisk(
        level=_level_from_score(score),
        score=round(score, 1),
        hypotheses=hypotheses,
        modifiers=modifiers,
    )


def composite_risk(
    *,
    interactions: dict | None,
    contraindications: list[Contraindication],
    flags: PatientFlags,
    disease: DiseaseRisk,
) -> tuple[RiskLevel, float]:
    """Roll everything into one 0-100 composite risk score (lower is safer)."""
    score = 0.0

    # Interactions — sum severity weights (capped).
    for inter in (interactions or {}).get("interactions", []) or []:
        score += _SEVERITY_WEIGHT[_interaction_severity(inter.get("severity", "moderate"))]
    score = min(score, 70.0)

    # Contraindications — each adds by its severity.
    for c in contraindications:
        score += _SEVERITY_WEIGHT.get(c.severity, 12.0) * 0.6

    # Patient fragility — a small always-on component.
    score += 4.0 * len(flags.active_factors())

    # Disease severity contributes a fraction.
    score += disease.score * 0.15

    score = round(max(0.0, min(100.0, score)), 1)
    return _level_from_score(score), score
