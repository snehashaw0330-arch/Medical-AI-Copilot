"""Treatment editing for the Simulation Engine (pure).

Parses free-text medicine strings into :class:`MedicineItem`s and applies a
scenario's ordered :class:`MedicineChange` list — dosage change, replace, remove,
add — producing the *resulting* medicine list plus a human-readable description of
every edit (so the UI and report can show exactly what changed).

All functions are deterministic and side-effect free.
"""

from __future__ import annotations

import re

from backend.simulation.schemas import (
    ChangeAction,
    MedicineChange,
    MedicineItem,
)

# "Paracetamol 500mg", "Amoxicillin 250 mg tds", "Metformin 1g"
_DOSE_RE = re.compile(
    r"(?P<dose>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|g|ml|units?|iu)\b", re.IGNORECASE
)


def parse_medicine(text: str) -> MedicineItem:
    """Parse a free-text medicine string into a structured item."""
    raw = (text or "").strip()
    dose: float | None = None
    unit = "mg"
    m = _DOSE_RE.search(raw)
    if m:
        dose = float(m.group("dose"))
        unit = m.group("unit").lower()
    # Name = text with the dose token stripped out.
    name = _DOSE_RE.sub("", raw).strip(" -,\t")
    # Drop trailing frequency-ish words from the name for cleaner matching.
    name = re.sub(r"\b(od|bd|tds|qds|prn|daily|nocte|mane)\b.*$", "", name, flags=re.IGNORECASE).strip()
    return MedicineItem(name=name or raw, dose=dose, unit=unit, raw=raw)


def normalise(items: list) -> list[MedicineItem]:
    """Coerce a list of strings/dicts/items into :class:`MedicineItem`s."""
    out: list[MedicineItem] = []
    for it in items or []:
        if isinstance(it, MedicineItem):
            out.append(it)
        elif isinstance(it, str):
            out.append(parse_medicine(it))
        elif isinstance(it, dict):
            if it.get("dose") is not None or it.get("unit"):
                out.append(MedicineItem(**it))
            else:
                out.append(parse_medicine(it.get("name") or it.get("raw") or ""))
    return [m for m in out if m.name]


def _find(items: list[MedicineItem], target: str | None) -> int:
    """Index of the medicine whose name matches *target* (case-insensitive), or -1."""
    if not target:
        return -1
    t = target.lower().strip()
    for i, m in enumerate(items):
        if m.name.lower() == t or t in m.name.lower() or m.name.lower() in t:
            return i
    return -1


def apply_changes(
    baseline: list[MedicineItem], changes: list[MedicineChange]
) -> tuple[list[MedicineItem], list[str]]:
    """Apply the ordered changes to a copy of *baseline*.

    Returns ``(resulting_medicines, applied_change_descriptions)``.
    """
    result = [m.model_copy(deep=True) for m in baseline]
    applied: list[str] = []

    for ch in changes:
        if ch.action == ChangeAction.DOSAGE:
            idx = _find(result, ch.target)
            if idx == -1:
                applied.append(f"⚠ Could not find '{ch.target}' to change dose.")
                continue
            old = result[idx].label()
            if ch.dose is not None:
                result[idx].dose = ch.dose
            if ch.unit:
                result[idx].unit = ch.unit
            if ch.frequency:
                result[idx].frequency = ch.frequency
            applied.append(f"Changed dose: {old} → {result[idx].label()}")

        elif ch.action == ChangeAction.REPLACE:
            idx = _find(result, ch.target)
            new = MedicineItem(
                name=ch.name or "?", dose=ch.dose, unit=ch.unit or "mg", frequency=ch.frequency,
            )
            if idx == -1:
                result.append(new)
                applied.append(f"Added (replacement target not found): {new.label()}")
            else:
                old = result[idx].label()
                result[idx] = new
                applied.append(f"Replaced: {old} → {new.label()}")

        elif ch.action == ChangeAction.REMOVE:
            idx = _find(result, ch.target)
            if idx == -1:
                applied.append(f"⚠ Could not find '{ch.target}' to remove.")
                continue
            removed = result.pop(idx)
            applied.append(f"Removed: {removed.label()}")

        elif ch.action == ChangeAction.ADD:
            new = MedicineItem(
                name=ch.name or ch.target or "?", dose=ch.dose,
                unit=ch.unit or "mg", frequency=ch.frequency,
            )
            if _find(result, new.name) != -1:
                applied.append(f"⚠ '{new.name}' already present; not added again.")
                continue
            result.append(new)
            applied.append(f"Added: {new.label()}")

    return result, applied


def names(items: list[MedicineItem]) -> list[str]:
    """Bare medicine names (for interaction / disease analysis)."""
    return [m.name for m in items if m.name]
