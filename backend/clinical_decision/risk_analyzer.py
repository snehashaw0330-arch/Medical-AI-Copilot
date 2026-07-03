"""Risk scoring for the Clinical Decision Support module.

Pure functions (no I/O) that fuse the signals gathered elsewhere — the
drug-interaction sub-report, the rules-engine red flags, polypharmacy and
unresolved medicines — into a single 0..100 ``risk_score`` and a four-level
:class:`RiskLevel` (low / moderate / high / critical).

The scoring is deliberately transparent and monotonic: the most dangerous input
dominates (a single critical red flag forces a CRITICAL report), while lesser
signals accumulate additively toward the score. This mirrors how the
drug-interaction module already takes the *max* severity as the headline.
"""

from __future__ import annotations

from backend.clinical_decision.rules_engine import RuleFindings
from backend.clinical_decision.schemas import RedFlag, RiskLevel

# Numeric rank so we can compare / take the max. Higher = more dangerous.
RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 1,
    RiskLevel.MODERATE: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}

# Interaction severities (5-level "none".."critical") mapped onto the CDSS scale.
_INTERACTION_TO_RISK: dict[str, RiskLevel] = {
    "none": RiskLevel.LOW,
    "low": RiskLevel.LOW,
    "moderate": RiskLevel.MODERATE,
    "high": RiskLevel.HIGH,
    "critical": RiskLevel.CRITICAL,
}

# Baseline score contributed by each risk level when it is the *floor* implied
# by a hard signal (a red flag or the interaction severity).
_LEVEL_FLOOR_SCORE: dict[RiskLevel, float] = {
    RiskLevel.LOW: 15.0,
    RiskLevel.MODERATE: 45.0,
    RiskLevel.HIGH: 70.0,
    RiskLevel.CRITICAL: 90.0,
}


def _max_level(levels: list[RiskLevel]) -> RiskLevel:
    """Most dangerous level in the list (LOW when empty)."""
    if not levels:
        return RiskLevel.LOW
    return max(levels, key=lambda lv: RISK_RANK[lv])


def interaction_risk(interaction_report: dict | None) -> RiskLevel:
    """Translate the drug-interaction overall severity to a :class:`RiskLevel`."""
    overall = ((interaction_report or {}).get("overall_risk") or "none").lower()
    return _INTERACTION_TO_RISK.get(overall, RiskLevel.LOW)


def red_flag_counts(red_flags: list[RedFlag]) -> dict[str, int]:
    """Tally red flags per severity (for badges / summaries)."""
    counts = {lv.value: 0 for lv in RiskLevel}
    for f in red_flags:
        counts[f.severity.value] += 1
    return counts


def assess(
    findings: RuleFindings,
    interaction_report: dict | None,
) -> tuple[RiskLevel, float]:
    """Compute the overall (risk_level, risk_score) for a case.

    Returns
    -------
    (RiskLevel, float)
        The headline level and a 0..100 score. The level is driven by the most
        dangerous single signal; the score refines it with additive contributions
        so two moderate cases can still be told apart.
    """
    flag_levels = [f.severity for f in findings.red_flags]
    inter_level = interaction_risk(interaction_report)

    # Headline level = worst of (red flags, interaction severity).
    headline = _max_level(flag_levels + [inter_level])

    # Score starts at the floor implied by the headline level, then accrues
    # additive risk from the number and severity of contributing signals.
    score = _LEVEL_FLOOR_SCORE[headline]

    # Each additional red flag nudges the score up (weighted by its severity).
    for f in findings.red_flags:
        score += 3.0 * RISK_RANK[f.severity]

    # Possible risks and contraindications add smaller increments.
    score += 2.0 * len(findings.possible_risks)
    score += 2.5 * len(findings.contraindications)

    # Number of dataset-confirmed interactions (beyond the headline severity).
    n_interactions = len((interaction_report or {}).get("interactions", []) or [])
    score += 2.0 * n_interactions

    # A report with essentially no signal should read as genuinely low.
    if headline == RiskLevel.LOW and not findings.red_flags and n_interactions == 0:
        score = min(score, 20.0)

    return headline, round(min(score, 100.0), 1)
