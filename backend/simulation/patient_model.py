"""Patient modelling for the Simulation Engine (pure).

Applies a scenario's :class:`PatientChange` overrides onto a baseline
:class:`PatientState` to produce the *effective* patient a scenario is evaluated
for, and derives the clinical flags the risk / recommendation engines consult
(paediatric / geriatric, pregnancy, renal + hepatic impairment, low body weight).

Everything here is deterministic and side-effect free — the same inputs always
yield the same effective patient and the same derived flags, which keeps a
simulation reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.simulation.schemas import Organ, PatientChange, PatientState

_ORGAN_RANK = {Organ.NONE: 0, Organ.MILD: 1, Organ.MODERATE: 2, Organ.SEVERE: 3}


def apply_patient_change(base: PatientState, change: PatientChange | None) -> PatientState:
    """Return a new effective :class:`PatientState` with *change* applied."""
    if change is None:
        return base.model_copy(deep=True)

    eff = base.model_copy(deep=True)
    if change.age is not None:
        eff.age = change.age
    if change.weight_kg is not None:
        eff.weight_kg = change.weight_kg
    if change.pregnant is not None:
        eff.pregnant = change.pregnant
    if change.renal_disease is not None:
        eff.renal_disease = change.renal_disease
    if change.hepatic_disease is not None:
        eff.hepatic_disease = change.hepatic_disease

    # Allergies: additive union minus removals (case-insensitive).
    removals = {a.lower().strip() for a in change.allergies_remove}
    seen = {a.lower() for a in eff.allergies if a.lower() not in removals}
    merged = [a for a in eff.allergies if a.lower() not in removals]
    for a in change.allergies_add:
        if a.strip() and a.lower() not in seen:
            seen.add(a.lower())
            merged.append(a.strip())
    eff.allergies = merged
    return eff


@dataclass
class PatientFlags:
    """Derived clinical flags used by the risk + recommendation engines."""

    is_paediatric: bool = False          # < 12
    is_geriatric: bool = False           # >= 65
    is_pregnant: bool = False
    child_bearing_potential: bool = False
    renal_impaired: bool = False
    renal_severe: bool = False
    hepatic_impaired: bool = False
    hepatic_severe: bool = False
    low_body_weight: bool = False        # < 50 kg (dose-sensitive)
    allergies: tuple[str, ...] = ()

    def active_factors(self) -> list[str]:
        """Human-readable list of the risk-modifying factors that are present."""
        out: list[str] = []
        if self.is_paediatric:
            out.append("paediatric age")
        if self.is_geriatric:
            out.append("age ≥ 65")
        if self.is_pregnant:
            out.append("pregnancy")
        if self.renal_severe:
            out.append("severe renal impairment")
        elif self.renal_impaired:
            out.append("renal impairment")
        if self.hepatic_severe:
            out.append("severe hepatic impairment")
        elif self.hepatic_impaired:
            out.append("hepatic impairment")
        if self.low_body_weight:
            out.append("low body weight")
        if self.allergies:
            out.append(f"{len(self.allergies)} recorded allerg(y/ies)")
        return out


def derive_flags(p: PatientState) -> PatientFlags:
    """Compute the derived clinical flags for an effective patient state."""
    female = (p.gender or "").lower() == "female"
    return PatientFlags(
        is_paediatric=p.age is not None and p.age < 12,
        is_geriatric=p.age is not None and p.age >= 65,
        is_pregnant=bool(p.pregnant),
        child_bearing_potential=female and p.age is not None and 12 <= p.age <= 50,
        renal_impaired=_ORGAN_RANK[p.renal_disease] >= 1,
        renal_severe=_ORGAN_RANK[p.renal_disease] >= 3,
        hepatic_impaired=_ORGAN_RANK[p.hepatic_disease] >= 1,
        hepatic_severe=_ORGAN_RANK[p.hepatic_disease] >= 3,
        low_body_weight=p.weight_kg is not None and p.weight_kg < 50,
        allergies=tuple(a.lower().strip() for a in p.allergies if a.strip()),
    )
