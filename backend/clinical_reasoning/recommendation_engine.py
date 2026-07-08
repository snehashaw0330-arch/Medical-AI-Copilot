"""Final-recommendation synthesis for the reasoning pipeline (pure).

Given everything the pipeline gathered — the differential, the fired clinical
rules, the drug-interaction sub-report and the confidence breakdown — this engine
produces the report's action-oriented sections:

* :func:`build_recommendations` — graded clinical actions, each with a rationale;
* :func:`build_follow_up`       — safety-net / review suggestions with timeframes;
* :func:`build_references`      — the citations surfaced to the clinician;
* :func:`overall_risk`          — a single roll-up risk level for the header badge.

Every recommendation carries its own ``rationale`` so the UI can show *why* it was
suggested, and everything here is deterministic and side-effect free.
"""

from __future__ import annotations

from backend.clinical_reasoning.schemas import (
    ConfidenceBreakdown,
    DifferentialDiagnosis,
    EvidenceCard,
    FollowUp,
    MatchedRule,
    MedicalReference,
    Recommendation,
    RiskLevel,
)

_SEVERITY_ORDER = {
    RiskLevel.CRITICAL: 0, RiskLevel.HIGH: 1, RiskLevel.MODERATE: 2, RiskLevel.LOW: 3,
}


def overall_risk(rules: list[MatchedRule], interaction_report: dict | None) -> RiskLevel:
    """Roll up the single worst risk signal across rules + interactions."""
    worst = RiskLevel.LOW
    for r in rules:
        if _SEVERITY_ORDER[r.severity] < _SEVERITY_ORDER[worst]:
            worst = r.severity
    # Interaction sub-report may carry its own risk_level / severity.
    if interaction_report:
        raw = str(
            interaction_report.get("risk_level")
            or interaction_report.get("severity")
            or ""
        ).lower()
        mapped = {
            "critical": RiskLevel.CRITICAL, "high": RiskLevel.HIGH,
            "moderate": RiskLevel.MODERATE, "low": RiskLevel.LOW,
        }.get(raw)
        if mapped and _SEVERITY_ORDER[mapped] < _SEVERITY_ORDER[worst]:
            worst = mapped
    return worst


class RecommendationEngine:
    """Synthesises the final recommendation, follow-up and reference sections."""

    def build_recommendations(
        self,
        *,
        leading: DifferentialDiagnosis | None,
        rules: list[MatchedRule],
        interaction_report: dict | None,
        confidence: ConfidenceBreakdown,
        risk: RiskLevel,
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []

        # 1) Escalation driven by any critical red-flag rule.
        for rule in rules:
            if rule.severity == RiskLevel.CRITICAL:
                recs.append(Recommendation(
                    title="Escalate urgently",
                    detail=rule.rationale,
                    priority=RiskLevel.CRITICAL,
                    category="referral",
                    rationale=f"Triggered by the '{rule.name}' rule ({', '.join(rule.triggered_by)}).",
                ))

        # 2) Interaction management.
        if interaction_report and (interaction_report.get("interactions") or interaction_report.get("warnings")):
            n = len(interaction_report.get("interactions") or [])
            recs.append(Recommendation(
                title="Review the flagged drug interactions",
                detail="Reconcile the medication list and adjust or space doses where indicated.",
                priority=RiskLevel.HIGH if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else RiskLevel.MODERATE,
                category="management",
                rationale=f"The drug-interaction analysis flagged {n} interaction(s).",
            ))

        # 3) Diagnosis-directed workup or confirmation.
        if leading is not None:
            if confidence.overall >= 60:
                recs.append(Recommendation(
                    title=f"Manage for {leading.disease}",
                    detail=f"Proceed with a management plan appropriate for {leading.disease}, guided by the evidence below.",
                    priority=RiskLevel.MODERATE,
                    category="management",
                    rationale=f"{leading.disease} is the leading diagnosis at {leading.confidence:.0f}% with {confidence.level.value.replace('_', ' ')} overall confidence.",
                ))
            else:
                recs.append(Recommendation(
                    title=f"Confirm the working diagnosis of {leading.disease}",
                    detail="Confidence is limited — gather the missing information before committing to a plan.",
                    priority=RiskLevel.MODERATE,
                    category="management",
                    rationale="Overall confidence is below the threshold for a definitive plan.",
                ))

        # 4) Address low confidence explicitly.
        if confidence.missing_information:
            recs.append(Recommendation(
                title="Obtain additional information",
                detail="Collecting the following would materially improve diagnostic certainty: "
                       + ", ".join(confidence.missing_information) + ".",
                priority=RiskLevel.LOW,
                category="monitoring",
                rationale="These inputs were absent from the confidence calculation.",
            ))

        # 5) Age/renal/pregnancy cautions become monitoring recommendations.
        for rule in rules:
            if rule.category in ("age", "renal", "pregnancy") and rule.severity != RiskLevel.CRITICAL:
                recs.append(Recommendation(
                    title=rule.name,
                    detail=rule.rationale,
                    priority=rule.severity,
                    category="monitoring",
                    rationale=f"Triggered by {', '.join(rule.triggered_by)}.",
                ))

        # Always end with the safety fallback.
        recs.append(Recommendation(
            title="Clinician verification required",
            detail="This automated reasoning is a decision-support aid; a qualified clinician must confirm every step before acting.",
            priority=RiskLevel.LOW,
            category="management",
            rationale="Platform safety policy — reasoning is never the sole basis for a decision.",
        ))

        # Sort by priority, keep order stable within a priority band.
        recs.sort(key=lambda r: _SEVERITY_ORDER[r.priority])
        return recs

    def build_follow_up(
        self, *, risk: RiskLevel, leading: DifferentialDiagnosis | None,
        rules: list[MatchedRule],
    ) -> list[FollowUp]:
        out: list[FollowUp] = []
        if risk == RiskLevel.CRITICAL:
            out.append(FollowUp(
                action="Seek emergency assessment now",
                timeframe="immediately",
                reason="A critical red-flag was identified.",
            ))
        elif risk == RiskLevel.HIGH:
            out.append(FollowUp(
                action="Arrange clinical review",
                timeframe="within 24–48 hours",
                reason="A high-severity risk signal was present.",
            ))
        else:
            out.append(FollowUp(
                action="Routine review",
                timeframe="within 1–2 weeks",
                reason="Reassess response to treatment and any new symptoms.",
            ))

        if leading is not None:
            out.append(FollowUp(
                action=f"Reassess the working diagnosis of {leading.disease}",
                timeframe="at the next visit",
                reason="Confirm the diagnosis holds and treatment is effective.",
            ))

        if any(r.category == "interaction" for r in rules):
            out.append(FollowUp(
                action="Monitor for adverse effects of the interacting drugs",
                timeframe="ongoing",
                reason="An interaction rule fired for this medication list.",
            ))
        out.append(FollowUp(
            action="Return sooner if symptoms worsen or new red-flags appear",
            timeframe="safety-net",
            reason="Standard safety-netting advice.",
        ))
        return out

    def build_references(
        self, *, evidence: list[EvidenceCard], rules: list[MatchedRule],
        used_model: bool, used_interactions: bool,
    ) -> list[MedicalReference]:
        refs: list[MedicalReference] = []
        for card in evidence[:8]:
            refs.append(MedicalReference(
                label=card.title,
                source=card.source or "Knowledge base",
                detail=(card.snippet[:160] + "…") if len(card.snippet) > 160 else card.snippet,
            ))
        if used_model:
            refs.append(MedicalReference(
                label="Disease-prediction model",
                source="Internal ML model",
                detail="Symptom-driven differential from the trained disease classifier.",
            ))
        if used_interactions:
            refs.append(MedicalReference(
                label="Drug-interaction dataset",
                source="Internal interaction knowledge base",
                detail="Documented drug–drug interactions and per-drug warnings.",
            ))
        if rules:
            refs.append(MedicalReference(
                label="Clinical rules engine",
                source="Curated deterministic rules",
                detail=f"{len(rules)} rule(s) fired for this case.",
            ))
        return refs


_ENGINE: RecommendationEngine | None = None


def get_engine() -> RecommendationEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RecommendationEngine()
    return _ENGINE
