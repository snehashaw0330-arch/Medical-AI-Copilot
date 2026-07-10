"""Metrics + confidence + hallucination-risk scoring (pure, auditable).

Rolls the per-claim verdicts, citations and evidence into the headline numbers the
"Evidence Verification" panel renders:

* **Evidence coverage %** — share of claims the evidence supports (weak counts
  half).
* **Citation strength** — average strength of the citations that were built.
* **Hallucination risk score + category** — driven mostly by the unsupported /
  contradicted claim ratio, with a five-level category (very low → critical).
* **Confidence score** — a weighted blend of coverage, citation strength,
  retrieval quality and the inverse of the hallucination risk, with a full
  component breakdown so the number is explainable.

Everything is deterministic: the same claims + evidence always yield the same
metrics.
"""

from __future__ import annotations

from backend.evidence_verification.schemas import (
    Citation,
    Claim,
    ClaimSupport,
    ConfidenceBreakdown,
    ConfidenceComponent,
    EvidenceDocument,
    HallucinationRisk,
    VerificationMetrics,
)

_CONF_WEIGHTS = {
    "evidence_coverage": 0.35,
    "citation_strength": 0.25,
    "retrieval_quality": 0.20,
    "low_hallucination": 0.20,
}


def _risk_category(score: float) -> HallucinationRisk:
    if score < 10:
        return HallucinationRisk.VERY_LOW
    if score < 25:
        return HallucinationRisk.LOW
    if score < 50:
        return HallucinationRisk.MEDIUM
    if score < 75:
        return HallucinationRisk.HIGH
    return HallucinationRisk.CRITICAL


def _conf_level(overall: float) -> str:
    if overall >= 85:
        return "very_high"
    if overall >= 68:
        return "high"
    if overall >= 45:
        return "moderate"
    if overall >= 25:
        return "low"
    return "very_low"


def _c(key: str, score: float, note: str) -> ConfidenceComponent:
    score = round(max(0.0, min(100.0, score)), 1)
    w = _CONF_WEIGHTS[key]
    return ConfidenceComponent(name=key, weight=w, score=score,
                               contribution=round(w * score, 1), note=note)


def compute(
    *,
    claims: list[Claim],
    citations: list[Citation],
    evidence: list[EvidenceDocument],
    missing_reference_count: int,
    retrieval_confidence: float,
) -> tuple[VerificationMetrics, ConfidenceBreakdown, str]:
    """Return ``(metrics, confidence_breakdown, verdict_text)``."""
    total = len(claims)
    supported = sum(1 for c in claims if c.support == ClaimSupport.SUPPORTED)
    weak = sum(1 for c in claims if c.support == ClaimSupport.WEAK)
    unsupported = sum(1 for c in claims if c.support == ClaimSupport.UNSUPPORTED)
    contradicted = sum(1 for c in claims if c.support == ClaimSupport.CONTRADICTED)

    if total == 0:
        # Nothing verifiable — neutral/unknown posture, not falsely confident.
        metrics = VerificationMetrics(
            evidence_coverage=0.0, citation_strength=0.0, confidence=0.0,
            hallucination_risk_score=50.0, hallucination_risk=HallucinationRisk.MEDIUM,
            total_claims=0, missing_reference_count=missing_reference_count,
        )
        breakdown = ConfidenceBreakdown(
            overall=0.0, level="very_low",
            rationale="No verifiable factual claims were found in the response.",
        )
        return metrics, breakdown, "No verifiable claims to check."

    coverage = 100.0 * (supported + 0.5 * weak) / total
    citation_strength = round(sum(c.strength for c in citations) / len(citations), 1) if citations else 0.0

    # Hallucination risk (0..100, higher = riskier).
    unsupported_pct = 100.0 * unsupported / total
    weak_pct = 100.0 * weak / total
    contradiction_penalty = min(25.0, 12.5 * contradicted)
    evidence_penalty = 20.0 if not evidence else max(0.0, (0.6 - retrieval_confidence) * 20.0)
    risk_score = round(min(100.0, max(0.0,
        0.60 * unsupported_pct + 0.20 * weak_pct + contradiction_penalty + evidence_penalty
    )), 1)
    risk = _risk_category(risk_score)

    # Confidence breakdown.
    components = [
        _c("evidence_coverage", coverage, f"{supported}/{total} claim(s) supported."),
        _c("citation_strength", citation_strength,
           f"{len(citations)} citation(s) built." if citations else "No citations built."),
        _c("retrieval_quality", min(100.0, retrieval_confidence * 100.0 if evidence else 0.0),
           f"{len(evidence)} evidence document(s) retrieved."),
        _c("low_hallucination", 100.0 - risk_score, f"Hallucination risk {risk.value.replace('_', ' ')}."),
    ]
    overall = round(sum(c.contribution for c in components), 1)
    overall = max(0.0, min(100.0, overall))
    level = _conf_level(overall)

    metrics = VerificationMetrics(
        evidence_coverage=round(coverage, 1),
        citation_strength=citation_strength,
        confidence=overall,
        hallucination_risk_score=risk_score,
        hallucination_risk=risk,
        total_claims=total, supported_claims=supported, weak_claims=weak,
        unsupported_claims=unsupported, contradicted_claims=contradicted,
        missing_reference_count=missing_reference_count,
    )

    strongest = max(components, key=lambda c: c.contribution)
    rationale = (
        f"{coverage:.0f}% evidence coverage across {total} claim(s); hallucination "
        f"risk is {risk.value.replace('_', ' ')}. Strongest confidence factor: "
        f"{strongest.name.replace('_', ' ')} ({strongest.score:.0f}/100)."
    )
    breakdown = ConfidenceBreakdown(overall=overall, level=level, components=components, rationale=rationale)

    verdict = _verdict(risk, coverage, unsupported, contradicted)
    return metrics, breakdown, verdict


def _verdict(risk: HallucinationRisk, coverage: float, unsupported: int, contradicted: int) -> str:
    if contradicted:
        return (f"⚠ {contradicted} claim(s) appear to contradict the evidence — "
                f"treat this response with caution.")
    if risk in (HallucinationRisk.VERY_LOW, HallucinationRisk.LOW):
        return f"Response is well-grounded ({coverage:.0f}% evidence coverage)."
    if risk == HallucinationRisk.MEDIUM:
        return f"Response is partially grounded; {unsupported} claim(s) lack supporting evidence."
    return (f"High hallucination risk — {unsupported} unsupported claim(s); verify "
            f"before relying on this response.")
