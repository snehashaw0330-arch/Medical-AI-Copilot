"""Trend engine — classify a metric as improving / stable / worsening + series.

Pure functions. Given a time series of values it computes a least-squares slope,
the net change, and a direction — accounting for each metric's *polarity*
(``higher_is_better``): a rising health score is *improving*, a rising risk score
is *worsening*. Produces the :class:`TrendResult` shapes the charts render.
"""

from __future__ import annotations

from datetime import datetime

from backend.digital_twin.schemas import SeriesPoint, TrendDirection, TrendResult


def slope(values: list[float]) -> float:
    """Least-squares slope of ``values`` over their integer index (per step)."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((xs[i] - mx) * (values[i] - my) for i in range(n)) / denom


def classify(values: list[float], *, higher_is_better: bool, eps: float) -> tuple[TrendDirection, float]:
    """Return (direction, net-change). ``eps`` is the dead-band for 'stable'."""
    if len(values) < 2:
        return TrendDirection.STABLE, 0.0
    delta = values[-1] - values[0]
    if abs(delta) < eps:
        return TrendDirection.STABLE, round(delta, 2)
    positive = delta > 0
    improving = positive == higher_is_better
    return (TrendDirection.IMPROVING if improving else TrendDirection.WORSENING), round(delta, 2)


def build_trend(
    metric: str,
    points: list[tuple[datetime, float]],
    *,
    higher_is_better: bool = True,
    eps: float = 5.0,
    label_fmt=None,
) -> TrendResult:
    """Assemble a :class:`TrendResult` from timestamped points."""
    values = [v for _, v in points]
    direction, delta = classify(values, higher_is_better=higher_is_better, eps=eps)
    series = [
        SeriesPoint(timestamp=t, value=round(float(v), 2),
                    label=(label_fmt(v) if label_fmt else None))
        for t, v in points
    ]
    verb = {TrendDirection.IMPROVING: "improving", TrendDirection.STABLE: "stable",
            TrendDirection.WORSENING: "worsening"}[direction]
    summary = (f"{metric.replace('_', ' ').title()} is {verb}"
               + (f" ({delta:+.1f})" if len(values) >= 2 and direction != TrendDirection.STABLE else "")
               + ".")
    return TrendResult(
        metric=metric, direction=direction, delta=delta,
        higher_is_better=higher_is_better, series=series, summary=summary,
    )
