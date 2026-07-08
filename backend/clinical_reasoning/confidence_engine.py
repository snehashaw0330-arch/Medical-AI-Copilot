"""Confidence scoring for the reasoning pipeline (pure, auditable).

Rather than emit a single opaque number, this engine produces a *weighted
breakdown*: several named components (input completeness, model certainty,
evidence grounding, rule agreement, differential separation), each with its own
0-100 sub-score and the points it contributed to the total. This is what lets the
UI render a confidence meter *and* explain it — a core product requirement.

The module is pure and deterministic so the same inputs always yield the same
breakdown, which keeps the reasoning reproducible and testable.
"""

from __future__ import annotations

from backend.clinical_reasoning.schemas import (
    ConfidenceBreakdown,
    ConfidenceComponent,
    ConfidenceLevel,
    DifferentialDiagnosis,
    MatchedRule,
)

# Component weights (sum to 1.0). Tunable without touching the maths.
_WEIGHTS = {
    "input_completeness": 0.20,
    "model_certainty": 0.30,
    "evidence_grounding": 0.20,
    "rule_agreement": 0.15,
    "differential_separation": 0.15,
}


def _level(overall: float) -> ConfidenceLevel:
    if overall >= 85:
        return ConfidenceLevel.VERY_HIGH
    if overall >= 68:
        return ConfidenceLevel.HIGH
    if overall >= 45:
        return ConfidenceLevel.MODERATE
    if overall >= 25:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.VERY_LOW


def _input_completeness(
    *, has_symptoms: bool, has_medicines: bool, has_age: bool,
    has_gender: bool, has_disease_or_dx: bool,
) -> tuple[float, list[str]]:
    """Score how much of the useful input was provided, and what is missing."""
    present = 0
    missing: list[str] = []
    checks = [
        (has_symptoms, "symptoms"),
        (has_medicines, "current medicines"),
        (has_age, "patient age"),
        (has_gender, "patient gender"),
        (has_disease_or_dx, "a working diagnosis"),
    ]
    for ok, label in checks:
        if ok:
            present += 1
        else:
            missing.append(label)
    return (present / len(checks)) * 100.0, missing


class ConfidenceEngine:
    """Computes the weighted confidence breakdown for one reasoning report."""

    def compute(
        self,
        *,
        hypotheses: list[DifferentialDiagnosis],
        rules: list[MatchedRule],
        evidence_confidence: float,       # 0..1 from the evidence engine
        evidence_count: int,
        has_symptoms: bool,
        has_medicines: bool,
        has_age: bool,
        has_gender: bool,
        has_disease_or_dx: bool,
        disease_predicted: bool,
    ) -> ConfidenceBreakdown:
        components: list[ConfidenceComponent] = []
        missing: list[str] = []

        # 1) Input completeness -------------------------------------------
        ic_score, ic_missing = _input_completeness(
            has_symptoms=has_symptoms, has_medicines=has_medicines,
            has_age=has_age, has_gender=has_gender,
            has_disease_or_dx=has_disease_or_dx,
        )
        missing.extend(ic_missing)
        components.append(self._component(
            "input_completeness", ic_score,
            note=("All key inputs present." if not ic_missing
                  else f"Missing: {', '.join(ic_missing)}."),
        ))

        # 2) Model certainty ----------------------------------------------
        leading = hypotheses[0] if hypotheses else None
        mc_score = leading.confidence if leading else 0.0
        if not disease_predicted and leading is None:
            mc_note = "No diagnosis could be derived from the inputs."
        elif leading and leading.source in ("input", "diagnosis"):
            mc_score = max(mc_score, 70.0)
            mc_note = "Working diagnosis supplied by the caller."
        else:
            mc_note = (f"Leading model probability {mc_score:.0f}%."
                       if leading else "No model prediction available.")
        components.append(self._component("model_certainty", mc_score, note=mc_note))

        # 3) Evidence grounding -------------------------------------------
        eg_score = min(100.0, evidence_confidence * 100.0)
        if evidence_count == 0:
            eg_score = 0.0
            eg_note = "No knowledge-base evidence retrieved."
            missing.append("supporting knowledge-base evidence")
        else:
            eg_note = f"{evidence_count} evidence document(s) grounded this case."
        components.append(self._component("evidence_grounding", eg_score, note=eg_note))

        # 4) Rule agreement -----------------------------------------------
        # Rules that fire increase certainty about *risk*, but conflicting
        # red-flags (critical severity) reduce diagnostic certainty. We reward
        # having *some* corroborating rules and lightly penalise critical alerts.
        critical = sum(1 for r in rules if r.severity.value == "critical")
        supportive = len(rules) - critical
        ra_score = min(100.0, 40.0 + supportive * 20.0 - critical * 15.0)
        ra_score = max(0.0, ra_score)
        ra_note = (f"{len(rules)} rule(s) fired"
                   + (f", {critical} critical" if critical else "")
                   + "." if rules else "No clinical rules fired.")
        components.append(self._component("rule_agreement", ra_score, note=ra_note))

        # 5) Differential separation --------------------------------------
        # A leading diagnosis that clearly outscores the runner-up is more
        # trustworthy than a tight cluster of near-equal candidates.
        if len(hypotheses) >= 2:
            gap = max(0.0, hypotheses[0].confidence - hypotheses[1].confidence)
            ds_score = min(100.0, 30.0 + gap * 1.4)
            ds_note = f"Leading candidate is {gap:.0f} points clear of the next."
            if gap < 10:
                missing.append("more distinguishing symptoms")
        elif len(hypotheses) == 1:
            ds_score = 70.0
            ds_note = "A single candidate with no competing differential."
        else:
            ds_score = 0.0
            ds_note = "No differential could be formed."
        components.append(self._component("differential_separation", ds_score, note=ds_note))

        # Weighted total ---------------------------------------------------
        overall = sum(c.contribution for c in components)
        overall = round(max(0.0, min(100.0, overall)), 1)
        level = _level(overall)

        # De-duplicate missing while preserving order.
        seen: set[str] = set()
        missing_unique = [m for m in missing if not (m in seen or seen.add(m))]

        rationale = self._rationale(level, components, missing_unique)
        return ConfidenceBreakdown(
            overall=overall, level=level, components=components,
            missing_information=missing_unique, rationale=rationale,
        )

    # -- helpers -----------------------------------------------------------
    def _component(self, key: str, score: float, note: str = "") -> ConfidenceComponent:
        score = round(max(0.0, min(100.0, score)), 1)
        weight = _WEIGHTS[key]
        return ConfidenceComponent(
            name=key, weight=weight, score=score,
            contribution=round(weight * score, 1), note=note,
        )

    def _rationale(
        self, level: ConfidenceLevel, components: list[ConfidenceComponent],
        missing: list[str],
    ) -> str:
        strongest = max(components, key=lambda c: c.contribution, default=None)
        weakest = min(components, key=lambda c: c.contribution, default=None)
        parts = [f"Overall confidence is {level.value.replace('_', ' ')}."]
        if strongest:
            parts.append(
                f"Strongest support came from {strongest.name.replace('_', ' ')} "
                f"({strongest.score:.0f}/100)."
            )
        if weakest and weakest is not strongest:
            parts.append(
                f"The weakest link was {weakest.name.replace('_', ' ')} "
                f"({weakest.score:.0f}/100)."
            )
        if missing:
            parts.append(f"Confidence would improve with: {', '.join(missing)}.")
        return " ".join(parts)


_ENGINE: ConfidenceEngine | None = None


def get_engine() -> ConfidenceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ConfidenceEngine()
    return _ENGINE
