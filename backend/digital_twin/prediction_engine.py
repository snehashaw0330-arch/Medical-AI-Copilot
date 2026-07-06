"""Prediction engine — short-horizon forecast of where the patient is heading.

Pure. Fits a least-squares trend to the health-score series and extrapolates one
step ahead, translating the projected score into a projected risk level. The
forecast ``confidence`` grows with the amount of history behind it (a single data
point yields no real forecast) and is reported honestly.
"""

from __future__ import annotations

from backend.digital_twin.schemas import Prediction, RiskLevel, TrendDirection
from backend.digital_twin.trend_engine import slope


def _risk_from_score(score: float) -> RiskLevel:
    if score >= 75:
        return RiskLevel.LOW
    if score >= 55:
        return RiskLevel.MEDIUM
    if score >= 35:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def forecast(health_values: list[float]) -> Prediction:
    """Project the next health score + risk from the health-score series."""
    if not health_values:
        return Prediction(summary="Not enough history to forecast.", confidence=0.0)
    if len(health_values) < 2:
        current = health_values[-1]
        return Prediction(
            projected_health_score=round(current, 1),
            projected_risk=_risk_from_score(current),
            direction=TrendDirection.STABLE,
            confidence=0.15,
            summary="Only one analysis on record — forecast will sharpen as more data arrives.",
        )

    m = slope(health_values)
    last = health_values[-1]
    projected = max(0.0, min(100.0, last + m))  # one step ahead
    # Confidence grows with history length, capped.
    confidence = round(min(0.9, 0.3 + 0.12 * (len(health_values) - 1)), 2)

    if abs(m) < 1.0:
        direction = TrendDirection.STABLE
        verb = "hold steady around"
    elif m > 0:
        direction = TrendDirection.IMPROVING
        verb = "continue improving toward"
    else:
        direction = TrendDirection.WORSENING
        verb = "decline toward"

    return Prediction(
        projected_health_score=round(projected, 1),
        projected_risk=_risk_from_score(projected),
        direction=direction,
        horizon="next visit",
        confidence=confidence,
        summary=f"On current trends, the health score is projected to {verb} "
                f"{projected:.0f}/100 by the next visit.",
    )
