"""Explainability synthesis for the reasoning pipeline (pure).

This engine turns the raw disease predictions and case context into the two
things the product's explainability requirements demand:

1. A **differential diagnosis** — the ranked candidates, each tagged
   ``leading`` / ``considered`` / ``rejected`` with explicit supporting facts,
   facts against, and a *rejection reason* for the ones that were dropped.
2. A **ReasoningExplanation** for the leading diagnosis that answers, in one
   place: why this disease, which symptoms contributed, which medicines
   influenced it, which documents were used, which rules matched, which
   alternatives were considered/rejected, the confidence breakdown, and what
   information is missing.

Everything here is deterministic and derives only from data already gathered by
the pipeline — it never calls a model or an external service itself.
"""

from __future__ import annotations

from backend.clinical_reasoning.schemas import (
    ConfidenceBreakdown,
    DiagnosisStatus,
    DifferentialDiagnosis,
    EvidenceCard,
    MatchedRule,
    MedicineInsight,
    ReasoningExplanation,
    SymptomContribution,
)

# A candidate whose confidence trails the leader by more than this is rejected.
_REJECT_GAP = 20.0
# Absolute floor: anything below this cannot be the leading diagnosis.
_MIN_LEADING = 1.0


class ExplanationEngine:
    """Builds the differential and the leading-diagnosis explanation."""

    # -- differential ------------------------------------------------------
    def build_differential(
        self, predictions: list[dict], reported_symptoms: list[str],
    ) -> list[DifferentialDiagnosis]:
        """Rank predictions and tag each with a status + rejection reasoning.

        ``predictions`` is a list of dicts with keys: ``disease``, ``confidence``
        (0..100), ``matched_symptoms`` (list[str]), ``explanation`` (str),
        ``source`` (str).
        """
        if not predictions:
            return []

        reported = [s.lower() for s in reported_symptoms]
        ranked = sorted(predictions, key=lambda p: p.get("confidence", 0.0), reverse=True)
        leader_conf = ranked[0].get("confidence", 0.0)

        out: list[DifferentialDiagnosis] = []
        for i, pred in enumerate(ranked):
            matched = [m.lower() for m in pred.get("matched_symptoms", [])]
            conf = float(pred.get("confidence", 0.0))
            supporting = [f"reports {m}" for m in matched] or (
                ["symptom pattern is consistent with this condition"] if reported else []
            )
            against = [
                f"does not explain reported '{s}'"
                for s in reported if s not in matched
            ][:4]

            if i == 0 and conf >= _MIN_LEADING:
                status = DiagnosisStatus.LEADING
                reason = ""
            elif leader_conf - conf > _REJECT_GAP or conf < _MIN_LEADING:
                status = DiagnosisStatus.REJECTED
                reason = self._rejection_reason(pred, ranked[0], matched, reported)
            else:
                status = DiagnosisStatus.CONSIDERED
                reason = ""

            out.append(DifferentialDiagnosis(
                disease=pred.get("disease", "Unknown"),
                confidence=round(conf, 1),
                status=status,
                supporting=supporting,
                against=against,
                rejection_reason=reason,
                source=pred.get("source", "model"),
            ))
        return out

    def _rejection_reason(
        self, pred: dict, leader: dict, matched: list[str], reported: list[str],
    ) -> str:
        gap = leader.get("confidence", 0.0) - pred.get("confidence", 0.0)
        leader_name = leader.get("disease", "the leading candidate")
        if not matched and reported:
            return (f"None of the reported symptoms are typical for this condition; "
                    f"{leader_name} explains the presentation better (by {gap:.0f} points).")
        missing = [s for s in reported if s not in matched]
        if missing:
            return (f"Explains fewer of the reported symptoms than {leader_name} "
                    f"(unaccounted: {', '.join(missing[:3])}); {gap:.0f} points lower.")
        return (f"Lower calibrated probability than {leader_name} "
                f"(by {gap:.0f} points) with no distinguishing features.")

    # -- symptom contributions --------------------------------------------
    def symptom_contributions(
        self, leading: DifferentialDiagnosis | None, reported_symptoms: list[str],
        resolved_symptoms: list[dict] | None = None,
    ) -> list[SymptomContribution]:
        """Attribute a normalised weight to each reported symptom for the leader."""
        if not reported_symptoms:
            return []
        matched_lower = {s.lower() for s in getattr(leading, "supporting", [])} if leading else set()
        # Build a quick lookup of which inputs resolved to a known symptom.
        resolved_map: dict[str, bool] = {}
        for r in (resolved_symptoms or []):
            inp = str(r.get("input", "")).lower()
            resolved_map[inp] = r.get("matched") is not None

        # Contributing symptoms are those the leader's matched list referenced.
        leading_matched = set()
        if leading:
            for s in leading.supporting:
                # supporting entries look like "reports <symptom>"
                leading_matched.add(s.replace("reports ", "").lower())

        contribs: list[SymptomContribution] = []
        n_matched = sum(1 for s in reported_symptoms if s.lower() in leading_matched) or 1
        for s in reported_symptoms:
            sl = s.lower()
            is_match = sl in leading_matched
            weight = round((1.0 / n_matched) if is_match else 0.0, 3)
            note = ("typical of the leading diagnosis" if is_match
                    else ("recognised symptom, not specific to the leader"
                          if resolved_map.get(sl, True) else "not recognised by the model"))
            contribs.append(SymptomContribution(
                symptom=s, weight=weight,
                matched=resolved_map.get(sl, True), note=note,
            ))
        # Highest contributors first.
        contribs.sort(key=lambda c: c.weight, reverse=True)
        return contribs

    # -- medicine insights -------------------------------------------------
    def medicine_insights(
        self, medicines: list[str], resolved: list[str], unmatched: list[str],
        interaction_report: dict | None,
    ) -> list[MedicineInsight]:
        interacting: set[str] = set()
        if interaction_report:
            for inter in (interaction_report.get("interactions") or []):
                for p in (inter.get("pair") or inter.get("medicines") or []):
                    interacting.add(str(p).lower())

        resolved_lower = {r.lower() for r in resolved}
        unmatched_lower = {u.lower() for u in unmatched}
        out: list[MedicineInsight] = []
        for name in medicines:
            nl = name.lower()
            is_resolved = nl in resolved_lower or nl not in unmatched_lower
            resolved_name = next((r for r in resolved if r.lower() == nl), None)
            if nl in interacting:
                role, influence = "interacting", "flagged in a drug–drug interaction"
            elif not is_resolved:
                role, influence = "treatment", "could not be matched to the medicine database"
            else:
                role, influence = "treatment", "part of the current regimen; informs the clinical picture"
            out.append(MedicineInsight(
                name=name, resolved_name=resolved_name,
                matched=is_resolved, role=role, influence=influence,
            ))
        return out

    # -- full explanation --------------------------------------------------
    def build_explanation(
        self,
        *,
        differential: list[DifferentialDiagnosis],
        reported_symptoms: list[str],
        resolved_symptoms: list[dict] | None,
        medicines: list[str],
        resolved: list[str],
        unmatched: list[str],
        interaction_report: dict | None,
        evidence: list[EvidenceCard],
        rules: list[MatchedRule],
        confidence: ConfidenceBreakdown,
        leading_raw_explanation: str = "",
    ) -> ReasoningExplanation:
        leading = next((d for d in differential if d.status == DiagnosisStatus.LEADING), None)
        considered = [d for d in differential if d.status == DiagnosisStatus.CONSIDERED]
        rejected = [d for d in differential if d.status == DiagnosisStatus.REJECTED]

        contribs = self.symptom_contributions(leading, reported_symptoms, resolved_symptoms)
        med_insights = self.medicine_insights(medicines, resolved, unmatched, interaction_report)

        if leading is not None:
            top_syms = [c.symptom for c in contribs if c.weight > 0][:4]
            why = leading_raw_explanation or (
                f"{leading.disease} is the leading diagnosis at {leading.confidence:.0f}% because "
                + (f"the reported {', '.join(top_syms)} are characteristic of it"
                   if top_syms else "it best fits the available information")
                + (f", and it clearly outranks {len(rejected)} rejected alternative(s)"
                   if rejected else "")
                + "."
            )
        else:
            why = ("No single diagnosis could be established from the inputs; "
                   "the reasoning proceeded on the medication and rule findings alone.")

        return ReasoningExplanation(
            why_disease=why,
            contributing_symptoms=contribs,
            influencing_medicines=med_insights,
            rag_documents_used=evidence,
            matched_rules=rules,
            alternatives_considered=considered,
            rejected_alternatives=rejected,
            confidence_breakdown=confidence,
            missing_information=confidence.missing_information,
        )


_ENGINE: ExplanationEngine | None = None


def get_engine() -> ExplanationEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ExplanationEngine()
    return _ENGINE
