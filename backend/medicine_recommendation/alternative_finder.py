"""Finds alternatives + structured drug data from the existing medicine dataset.

This layer is the bridge between the recommendation module and the project's
shared :class:`~backend.ocr.medicine_intelligence.MedicineIndex` (the ~248k-row
Indian medicine dataset already used by OCR and Medicine Search). It reuses that
index — so the dataset is loaded once and matching stays consistent — and adds:

* medicine resolution (fuzzy match → canonical name + confidence),
* substitute / generic-equivalent extraction,
* same-class "similar medicine" discovery (via a lazily-built class index),
* available-strength parsing,
* and best-effort heuristics for the fields the dataset does not carry
  (prescription-required, storage, pregnancy, food) which RAG later refines.

Everything here is synchronous and CPU/pandas-bound; the async service calls it
through :func:`asyncio.to_thread` so the event loop is never blocked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from backend.ocr.medicine_intelligence import get_index, normalize

# Match threshold (0..100) below which we treat a name as "not confidently
# resolved" — we still return what we can but flag low confidence.
RESOLVE_THRESHOLD = 60.0

# Strength tokens like "500 mg", "10mg", "5 ml", "250mcg", "2%", "40 IU".
_STRENGTH_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|ml|g|gm|iu|%)\b", re.IGNORECASE
)

# Dosage forms we can detect in a name (used for storage hints).
_FORM_RE = re.compile(
    r"\b(tablet|tab|capsule|cap|syrup|suspension|susp|injection|inj|drops?|"
    r"cream|ointment|gel|solution|spray|sachet|powder|lotion|inhaler)\b",
    re.IGNORECASE,
)

# Therapeutic classes that almost always require a prescription in India.
_RX_THERAPEUTIC = {
    "anti infectives", "cardiac", "anti diabetic", "anti-diabetic",
    "respiratory", "neuro cns", "hormones", "anti neoplastics", "urology",
    "anti malarials", "vaccines", "blood related", "anti coagulants",
    "opthal otologicals", "gastro intestinal",
}

# A small set of common OTC molecule/brand roots (best-effort — confirm locally).
_OTC_ROOTS = {
    "paracetamol", "acetaminophen", "crocin", "dolo", "calpol", "cetirizine",
    "cetrizine", "loratadine", "antacid", "digene", "gelusil", "ors",
    "vitamin", "calcium", "saridon", "disprin", "benadryl", "vicks",
    "electral", "combiflam", "sinarest",
}


@dataclass
class ResolvedMedicine:
    """A resolved medicine plus everything the dataset knows about it."""

    detected: str
    resolved_name: str
    matched: bool
    score: float
    details: dict = field(default_factory=dict)


# ==========================================================================
# Resolution
# ==========================================================================
def resolve(name: str) -> ResolvedMedicine:
    """Resolve a detected/typed name to a canonical dataset medicine."""
    index = get_index()
    matches = index.search(name, limit=3)
    if not matches:
        return ResolvedMedicine(name, name, False, 0.0, {})
    best = matches[0]
    matched = best.score >= RESOLVE_THRESHOLD
    details = index.details(best.name) if matched else {}
    return ResolvedMedicine(
        detected=name,
        resolved_name=best.name if matched else name,
        matched=matched,
        score=round(best.score, 1),
        details=details,
    )


# ==========================================================================
# Structured-data helpers (pure, from the dataset row)
# ==========================================================================
def available_strengths(*texts: str) -> list[str]:
    """Extract unique strength tokens from a name and its substitutes."""
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for m in _STRENGTH_RE.findall(text or ""):
            token = re.sub(r"\s+", " ", m).strip().lower()
            # Normalise "500mg" → "500 mg" for display.
            token = re.sub(r"(\d)([a-z%])", r"\1 \2", token)
            if token not in seen:
                seen.add(token)
                found.append(token)
    return found


def detected_form(name: str) -> str | None:
    """Return the dosage form mentioned in the name, if any."""
    m = _FORM_RE.search(name or "")
    return m.group(1).lower() if m else None


def extract_generic(details: dict) -> str:
    """Best-effort generic/active identity from the dataset row.

    The dataset stores brand names; the closest structured signal is the
    Chemical Class (the salt/molecule family). Returned as an approximation —
    RAG and the pharmacist remain the source of truth for the exact molecule.
    """
    chem = (details.get("chemical_class") or "").strip()
    return chem


def prescription_required(details: dict, resolved_name: str) -> tuple[str, str]:
    """Heuristic Rx/OTC classification. Returns (value, note).

    value ∈ {"yes", "no", "unknown"}. This is a best-effort convenience signal,
    never a legal/clinical determination — the note makes that explicit.
    """
    name_norm = normalize(resolved_name)
    therapeutic = (details.get("therapeutic_class") or "").strip().lower()
    habit = (details.get("habit_forming") or "").strip().lower()

    if habit == "yes":
        return "yes", ("Habit-forming / scheduled medicine — a valid prescription "
                       "is required.")
    if any(root in name_norm for root in _OTC_ROOTS):
        return "no", ("Commonly available over the counter, but confirm with your "
                      "pharmacist for your region.")
    if therapeutic in _RX_THERAPEUTIC:
        return "yes", (f"Belongs to '{details.get('therapeutic_class')}', which "
                       "typically requires a prescription.")
    return "unknown", ("Prescription status could not be determined automatically "
                       "— please confirm with a pharmacist.")


def storage_instructions(form: str | None) -> str:
    """Standard, form-aware storage guidance (dataset carries none)."""
    base = ("Store below 30°C in a cool, dry place, away from direct sunlight and "
            "moisture. Keep out of the reach of children.")
    if form in {"syrup", "suspension", "susp", "drops", "solution"}:
        base += (" Do not freeze; once opened, use within the period stated on the "
                 "label and discard after that.")
    elif form in {"injection", "inj"}:
        base += " Some injectables need refrigeration (2–8°C) — check the label."
    elif form in {"cream", "ointment", "gel", "lotion"}:
        base += " Close the cap tightly after each use."
    return base


# ==========================================================================
# Alternatives + similar (same-class) discovery
# ==========================================================================
@lru_cache(maxsize=1)
def _class_index() -> dict[str, list[int]]:
    """Lazily build {normalised therapeutic class → row indices} once, cached.

    Iterates the shared dataframe a single time. Used to find "similar" medicines
    in the same therapeutic category quickly without re-scanning per request.
    """
    index = get_index()
    df = index.df
    by_class: dict[str, list[int]] = {}
    if "Therapeutic Class" not in df.columns:
        return by_class
    series = df["Therapeutic Class"].astype("string")
    for i, value in enumerate(series):
        if value is None:
            continue
        key = str(value).strip().lower()
        if key and key != "nan":
            by_class.setdefault(key, []).append(i)
    return by_class


def find_similar(details: dict, resolved_name: str, exclude: set[str], limit: int) -> list[tuple[str, float]]:
    """Medicines in the same therapeutic class. Returns [(name, relevance)]."""
    therapeutic = (details.get("therapeutic_class") or "").strip().lower()
    if not therapeutic:
        return []
    index = get_index()
    idxs = _class_index().get(therapeutic, [])
    if not idxs:
        return []

    resolved_norm = normalize(resolved_name)
    action = (details.get("action_class") or "").strip().lower()
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    # Iterate a bounded slice so a huge class doesn't cost too much.
    for i in idxs[: max(limit * 40, 200)]:
        name = str(index.df.iloc[i]["name"])
        norm = normalize(name)
        if not norm or norm == resolved_norm or norm in exclude or norm in seen:
            continue
        seen.add(norm)
        # Prefer same action-class matches (more mechanistically similar).
        row_action = str(index.df.iloc[i].get("Action Class", "") or "").strip().lower()
        relevance = 85.0 if action and row_action == action else 70.0
        out.append((name, relevance))
        if len(out) >= limit:
            break
    return out
