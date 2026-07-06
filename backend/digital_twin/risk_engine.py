"""Risk engine — predict the patient's future risk (low/medium/high/critical).

Pure. Combines the *latest* clinical risk level, drug-interaction severity and
clinical-warning burden into a 0..100 risk score, then nudges it by the health
trajectory (a worsening trend raises predicted risk; an improving one lowers it),
and maps the result to the four-level scale with the human-readable drivers.
"""

from __future__ import annotations

from backend.digital_twin.schemas import RiskAssessment, RiskLevel, TrendDirection

_RISK_SEVERITY = {"low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}
_INTER_SEVERITY = {"none": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}


def _level_from_score(score: float, *, force_critical: bool) -> RiskLevel:
    if force_critical or score >= 75:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def assess(encounters: list[dict], health_direction: TrendDirection) -> RiskAssessment:
    """Return the predicted future-risk assessment for the latest state."""
    if not encounters:
        return RiskAssessment(level=RiskLevel.LOW, score=0.0,
                              summary="No history available to assess risk.")

    latest = encounters[-1]
    risk_level = (latest.get("risk_level") or "").lower()
    interaction_risk = (latest.get("interaction_risk") or "none").lower()
    warn_count = len(latest.get("warnings", []) or []) + len(latest.get("red_flags", []) or [])

    risk_sev = _RISK_SEVERITY.get(risk_level, 0)
    inter_sev = _INTER_SEVERITY.get(interaction_risk, 0)

    score = risk_sev * 20 + inter_sev * 6 + min(warn_count, 5) * 4  # 0..124
    drivers: list[str] = []
    if risk_sev:
        drivers.append(f"Latest clinical risk level: {risk_level}.")
    if inter_sev:
        drivers.append(f"Drug-interaction severity: {interaction_risk}.")
    if warn_count:
        drivers.append(f"{warn_count} active clinical warning(s)/red flag(s).")

    # Trajectory adjustment.
    if health_direction == TrendDirection.WORSENING:
        score += 12
        drivers.append("Health trajectory is worsening over recent visits.")
    elif health_direction == TrendDirection.IMPROVING:
        score -= 10
        drivers.append("Health trajectory is improving over recent visits.")

    score = max(0.0, min(100.0, float(score)))
    force_critical = risk_level == "critical"
    level = _level_from_score(score, force_critical=force_critical)

    if not drivers:
        drivers.append("No significant risk factors detected in the latest analysis.")

    summary = {
        RiskLevel.LOW: "Low predicted risk — maintain routine follow-up.",
        RiskLevel.MEDIUM: "Moderate predicted risk — monitor and review soon.",
        RiskLevel.HIGH: "High predicted risk — clinical review is recommended.",
        RiskLevel.CRITICAL: "Critical predicted risk — urgent clinical attention advised.",
    }[level]

    return RiskAssessment(level=level, score=round(score, 1), drivers=drivers, summary=summary)
