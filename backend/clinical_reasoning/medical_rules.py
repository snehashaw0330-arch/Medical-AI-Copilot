"""Deterministic clinical rules for the reasoning pipeline.

This module is intentionally *pure* and side-effect free: given a
:class:`ReasoningContext` it returns the list of :class:`MatchedRule` objects that
fired, each with a plain-language rationale and the specific inputs that
triggered it. Keeping the rules declarative makes the reasoning fully auditable —
the UI can show exactly which rule matched and why, which is a core requirement of
the platform.

The rules here are a transparent, curated safety net (age/renal cautions, classic
red-flag symptom clusters, high-alert drug pairs, pregnancy cautions). They are
deliberately conservative and are *never* the sole basis for a recommendation —
they layer on top of the disease model, the drug-interaction dataset and the RAG
evidence, all of which the reasoning engine also consults.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.clinical_reasoning.schemas import MatchedRule, RiskLevel


# ==========================================================================
# Context passed to every rule
# ==========================================================================
@dataclass
class ReasoningContext:
    """Everything the rules (and downstream engines) need, normalised."""

    age: int | None = None
    gender: str | None = None
    symptoms: list[str] = field(default_factory=list)          # lowercased
    disease: str | None = None
    diagnosis: str | None = None
    medicines: list[str] = field(default_factory=list)         # as supplied
    resolved_medicines: list[str] = field(default_factory=list)  # lowercased
    unmatched_medicines: list[str] = field(default_factory=list)
    interaction_report: dict = field(default_factory=dict)

    # -- convenience views -------------------------------------------------
    def med_set(self) -> set[str]:
        names = {m.lower() for m in self.medicines}
        names |= {m.lower() for m in self.resolved_medicines}
        return names

    def symptom_set(self) -> set[str]:
        return {s.lower() for s in self.symptoms}


# ==========================================================================
# Rule catalogue
# ==========================================================================
# High-alert / classic interacting drug pairs (by generic substring). This is a
# transparent safety net layered on top of the full drug-interaction dataset.
_INTERACTION_PAIRS: list[tuple[set[str], str, RiskLevel]] = [
    ({"warfarin", "aspirin"}, "Additive bleeding risk (anticoagulant + antiplatelet).", RiskLevel.HIGH),
    ({"warfarin", "ibuprofen"}, "NSAID increases bleeding risk with warfarin.", RiskLevel.HIGH),
    ({"warfarin", "nsaid"}, "NSAID increases bleeding risk with warfarin.", RiskLevel.HIGH),
    ({"methotrexate", "ibuprofen"}, "NSAIDs reduce methotrexate clearance (toxicity).", RiskLevel.HIGH),
    ({"ace", "potassium"}, "ACE inhibitor + potassium raises hyperkalaemia risk.", RiskLevel.MODERATE),
    ({"metformin", "contrast"}, "Hold metformin around iodinated contrast (lactic acidosis).", RiskLevel.MODERATE),
    ({"ssri", "tramadol"}, "Serotonin syndrome risk (SSRI + tramadol).", RiskLevel.HIGH),
    ({"statin", "clarithromycin"}, "CYP3A4 inhibition raises statin myopathy risk.", RiskLevel.MODERATE),
]

# Red-flag symptom clusters that always warrant urgent review.
_RED_FLAG_CLUSTERS: list[tuple[set[str], str, RiskLevel]] = [
    ({"chest pain", "shortness of breath"}, "Chest pain with dyspnoea — exclude acute coronary syndrome / PE.", RiskLevel.CRITICAL),
    ({"chest pain", "sweating"}, "Chest pain with diaphoresis — exclude acute coronary syndrome.", RiskLevel.CRITICAL),
    ({"severe headache", "neck stiffness"}, "Headache with neck stiffness — exclude meningitis / SAH.", RiskLevel.CRITICAL),
    ({"fever", "neck stiffness"}, "Fever with neck stiffness — exclude meningitis.", RiskLevel.CRITICAL),
    ({"weakness", "slurred speech"}, "Focal deficit with speech change — exclude stroke.", RiskLevel.CRITICAL),
    ({"abdominal pain", "vomiting blood"}, "Abdominal pain with haematemesis — exclude GI bleed.", RiskLevel.HIGH),
]

# Single red-flag symptoms.
_RED_FLAG_SYMPTOMS: dict[str, tuple[str, RiskLevel]] = {
    "vomiting blood": ("Haematemesis warrants urgent assessment.", RiskLevel.HIGH),
    "blood in stool": ("GI bleeding warrants assessment.", RiskLevel.HIGH),
    "suicidal": ("Expressed self-harm risk requires immediate safeguarding.", RiskLevel.CRITICAL),
    "loss of consciousness": ("Syncope / LOC warrants urgent evaluation.", RiskLevel.HIGH),
}


def _fires(needle: str, haystack: set[str]) -> str | None:
    """Return the first member of *haystack* containing *needle*, else None."""
    for item in haystack:
        if needle in item:
            return item
    return None


# ==========================================================================
# Individual rule evaluators (each returns 0+ MatchedRule)
# ==========================================================================
def _age_rules(ctx: ReasoningContext) -> list[MatchedRule]:
    out: list[MatchedRule] = []
    meds = ctx.med_set()
    if ctx.age is None:
        return out
    if ctx.age >= 65 and meds:
        out.append(MatchedRule(
            id="age.elderly-polypharmacy",
            name="Elderly medication caution",
            category="age",
            severity=RiskLevel.MODERATE,
            rationale=("Patient is ≥65; renal/hepatic clearance and falls risk "
                       "warrant dose review and deprescribing where possible."),
            triggered_by=[f"age={ctx.age}", *sorted(meds)],
        ))
        if _fires("nsaid", meds) or _fires("ibuprofen", meds) or _fires("naproxen", meds):
            out.append(MatchedRule(
                id="age.elderly-nsaid",
                name="NSAID caution in the elderly",
                category="age",
                severity=RiskLevel.HIGH,
                rationale="NSAIDs in ≥65s carry higher GI-bleed and renal risk.",
                triggered_by=[f"age={ctx.age}", "NSAID"],
            ))
    if ctx.age <= 12 and meds:
        out.append(MatchedRule(
            id="age.paediatric-dosing",
            name="Paediatric dosing review",
            category="age",
            severity=RiskLevel.MODERATE,
            rationale="Paediatric patient — confirm weight-based dosing and formulation.",
            triggered_by=[f"age={ctx.age}"],
        ))
    return out


def _interaction_rules(ctx: ReasoningContext) -> list[MatchedRule]:
    out: list[MatchedRule] = []
    meds = ctx.med_set()
    for pair, rationale, sev in _INTERACTION_PAIRS:
        hits = [_fires(p, meds) for p in pair]
        if all(hits):
            out.append(MatchedRule(
                id=f"interaction.{'-'.join(sorted(pair))}",
                name="High-alert drug interaction",
                category="interaction",
                severity=sev,
                rationale=rationale,
                triggered_by=[h for h in hits if h],
            ))
    return out


def _red_flag_rules(ctx: ReasoningContext) -> list[MatchedRule]:
    out: list[MatchedRule] = []
    symptoms = ctx.symptom_set()
    for cluster, rationale, sev in _RED_FLAG_CLUSTERS:
        hits = [_fires(c, symptoms) for c in cluster]
        if all(hits):
            out.append(MatchedRule(
                id=f"redflag.{'-'.join(sorted(s.replace(' ', '_') for s in cluster))}",
                name="Red-flag symptom cluster",
                category="red-flag",
                severity=sev,
                rationale=rationale,
                triggered_by=[h for h in hits if h],
            ))
    for needle, (rationale, sev) in _RED_FLAG_SYMPTOMS.items():
        hit = _fires(needle, symptoms)
        if hit:
            out.append(MatchedRule(
                id=f"redflag.{needle.replace(' ', '_')}",
                name="Red-flag symptom",
                category="red-flag",
                severity=sev,
                rationale=rationale,
                triggered_by=[hit],
            ))
    return out


def _pregnancy_rules(ctx: ReasoningContext) -> list[MatchedRule]:
    out: list[MatchedRule] = []
    if (ctx.gender or "").lower() != "female" or ctx.age is None:
        return out
    if not (12 <= ctx.age <= 50):
        return out
    meds = ctx.med_set()
    teratogens = ["warfarin", "isotretinoin", "methotrexate", "ace", "valproate", "nsaid", "ibuprofen"]
    fired = [t for t in teratogens if _fires(t, meds)]
    if fired:
        out.append(MatchedRule(
            id="pregnancy.teratogen-caution",
            name="Pregnancy-category caution",
            category="pregnancy",
            severity=RiskLevel.HIGH,
            rationale=("Medication with pregnancy-safety concerns in a patient of "
                       "child-bearing potential — confirm pregnancy status."),
            triggered_by=fired,
        ))
    return out


def _renal_rules(ctx: ReasoningContext) -> list[MatchedRule]:
    """Fire when the diagnosis/symptoms suggest renal impairment plus renal-cleared drugs."""
    out: list[MatchedRule] = []
    text = " ".join([ctx.disease or "", ctx.diagnosis or "", *ctx.symptoms]).lower()
    if any(k in text for k in ("renal", "kidney", "ckd", "nephro")):
        meds = ctx.med_set()
        renal = [m for m in ("metformin", "nsaid", "ibuprofen", "gabapentin") if _fires(m, meds)]
        if renal:
            out.append(MatchedRule(
                id="renal.dose-adjust",
                name="Renal dose-adjustment caution",
                category="renal",
                severity=RiskLevel.HIGH,
                rationale="Renally-cleared drug in suspected renal impairment — review dose.",
                triggered_by=renal,
            ))
    return out


def _dataset_interaction_rules(ctx: ReasoningContext) -> list[MatchedRule]:
    """Surface interactions already found by the drug-interaction dataset as rules."""
    out: list[MatchedRule] = []
    report = ctx.interaction_report or {}
    for inter in (report.get("interactions") or [])[:8]:
        pair = inter.get("pair") or inter.get("medicines") or []
        sev_raw = str(inter.get("severity", "moderate")).lower()
        sev = {
            "critical": RiskLevel.CRITICAL, "high": RiskLevel.HIGH,
            "moderate": RiskLevel.MODERATE, "low": RiskLevel.LOW,
        }.get(sev_raw, RiskLevel.MODERATE)
        out.append(MatchedRule(
            id=f"dataset.{'-'.join(str(p).lower() for p in pair) or 'interaction'}",
            name="Documented drug interaction",
            category="interaction",
            severity=sev,
            rationale=inter.get("description") or inter.get("effect") or "Documented interaction.",
            triggered_by=[str(p) for p in pair],
        ))
    return out


# ==========================================================================
# Public entry point
# ==========================================================================
_RULE_FUNCS = (
    _age_rules,
    _interaction_rules,
    _red_flag_rules,
    _pregnancy_rules,
    _renal_rules,
    _dataset_interaction_rules,
)


def evaluate(ctx: ReasoningContext) -> list[MatchedRule]:
    """Run every rule against *ctx* and return the fired rules (deduped)."""
    fired: list[MatchedRule] = []
    seen: set[str] = set()
    for func in _RULE_FUNCS:
        try:
            for rule in func(ctx):
                if rule.id in seen:
                    continue
                seen.add(rule.id)
                fired.append(rule)
        except Exception:  # noqa: BLE001 — one bad rule never breaks the engine
            continue
    # Most severe first for display.
    order = {RiskLevel.CRITICAL: 0, RiskLevel.HIGH: 1, RiskLevel.MODERATE: 2, RiskLevel.LOW: 3}
    fired.sort(key=lambda r: order.get(r.severity, 9))
    return fired
