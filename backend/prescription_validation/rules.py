"""Pure prescription-safety knowledge for the validator.

This module holds *only* data and small pure helpers — no I/O, no async, no
framework code — so the rules are easy to read, audit and unit-test. It is the
single place a clinician/pharmacist would edit to tune what the validator flags.

Contents
--------
* :data:`UNSAFE_ABBREVIATIONS` — error-prone abbreviations (ISMP-style) with the
  reason they are dangerous and a safer alternative.
* :data:`BRAND_TO_INGREDIENT` — a small brand → active-ingredient map plus
  generic synonyms, used to catch the same active ingredient prescribed under
  two different names (therapeutic duplication).
* Scoring weights + thresholds and a couple of normalisation helpers.
"""

from __future__ import annotations

import re

from backend.prescription_validation.schemas import Severity

# ==========================================================================
# Scoring (Requirement 3) — penalty subtracted from a perfect 100 per issue.
# ==========================================================================
SEVERITY_PENALTY: dict[Severity, float] = {
    Severity.HIGH: 22.0,
    Severity.MEDIUM: 10.0,
    Severity.LOW: 4.0,
}

# Risk-grade cut-offs (Requirement 4). A single HIGH issue forces high_risk and
# any MEDIUM issue forces at least needs_review, regardless of the raw score.
SAFE_SCORE_FLOOR = 80.0        # score >= this AND no medium/high → safe
HIGH_RISK_SCORE_CEILING = 50.0  # score < this → high_risk

# Below this OCR row confidence (0..1) a medicine is flagged. Overridable via
# settings.VALIDATION_LOW_CONFIDENCE at the service layer.
DEFAULT_LOW_CONFIDENCE = 0.6
# A fuzzy match-score (0..100) at or below this makes a resolved name suspicious.
WEAK_MATCH_SCORE = 60.0


# ==========================================================================
# Error-prone abbreviations (Requirement 2: "unsafe abbreviations")
# --------------------------------------------------------------------------
# Each entry: compiled pattern → (label, why it is dangerous, safer form, sev).
# Patterns are matched against the combined prescription text. Word boundaries
# and case are chosen per-item because some are only dangerous in a given case
# (e.g. a bare "U" for units, or a trailing-zero dose like "1.0 mg").
# ==========================================================================
_ABBR_SPECS: list[tuple[str, int, str, str, str, Severity]] = [
    # pattern, regex-flags, label, reason, safer-form, severity
    (r"\bU\b", 0, "U (unit)",
     "The abbreviation 'U' for 'unit' is easily misread as a 0, 4 or 'cc', "
     "causing large overdoses.",
     "Write the word 'unit' in full.", Severity.HIGH),
    (r"\bIU\b", 0, "IU (international unit)",
     "'IU' can be mistaken for 'IV' (intravenous) or the number 10.",
     "Write 'international unit' in full.", Severity.HIGH),
    (r"\bMSO4\b|\bMgSO4\b|\bMS\b", 0, "MS / MSO4 / MgSO4",
     "'MS' is ambiguous and 'MSO4' (morphine) is confused with 'MgSO4' "
     "(magnesium sulfate) — a life-threatening mix-up.",
     "Write the full drug name (e.g. 'morphine sulfate').", Severity.HIGH),
    (r"\bQD\b|\bQ\.D\.", re.IGNORECASE, "QD (once daily)",
     "'QD' is misread as 'QID' (four times daily), quadrupling the dose.",
     "Write 'once daily' or 'every day'.", Severity.MEDIUM),
    (r"\bQOD\b|\bQ\.O\.D\.", re.IGNORECASE, "QOD (every other day)",
     "'QOD' is misread as 'QD' (daily) or 'QID' (four times daily).",
     "Write 'every other day'.", Severity.MEDIUM),
    (r"\bSC\b|\bSQ\b", 0, "SC / SQ (subcutaneous)",
     "'SC'/'SQ' can be read as 'SL' (sublingual) or '5 every'.",
     "Write 'subcutaneous' or 'subcut'.", Severity.MEDIUM),
    (r"\bTIW\b", re.IGNORECASE, "TIW (three times a week)",
     "'TIW' is misread as three times a day or twice a week.",
     "Write 'three times weekly'.", Severity.MEDIUM),
    (r"\bHS\b", 0, "HS (at bedtime)",
     "'HS' (bedtime) is confused with 'half-strength'.",
     "Write 'at bedtime'.", Severity.MEDIUM),
    (r"\bD/C\b", 0, "D/C (discharge / discontinue)",
     "'D/C' is ambiguous — it means both 'discharge' and 'discontinue'.",
     "Write 'discharge' or 'discontinue' explicitly.", Severity.MEDIUM),
    (r"\b[uµ]g\b", 0, "µg / ug (microgram)",
     "'µg'/'ug' is misread as 'mg' — a 1000-fold error.",
     "Write 'mcg'.", Severity.MEDIUM),
    (r"\bcc\b", re.IGNORECASE, "cc (cubic centimetre)",
     "'cc' is misread as 'U' (units) or '00'.",
     "Write 'mL'.", Severity.LOW),
    (r"\b(?:AD|AS|AU|OD|OS|OU)\b", 0, "AD/AS/AU · OD/OS/OU (ear/eye)",
     "These Latin ear/eye abbreviations are mixed up with each other, and 'OD' "
     "also means 'once daily' — ambiguous.",
     "Write 'right/left/both ear' or 'right/left/both eye'.", Severity.MEDIUM),
    (r"\d+\.0(?!\d)", 0, "Trailing zero (e.g. 1.0 mg)",
     "A trailing zero after a decimal (1.0) is misread as 10 when the point is "
     "missed — a tenfold overdose.",
     "Never use a trailing zero — write '1 mg', not '1.0 mg'.", Severity.HIGH),
    (r"(?<![\d.])\.\d", 0, "Naked decimal (e.g. .5 mg)",
     "A leading decimal without a zero ('.5') is misread as 5 — a tenfold "
     "overdose.",
     "Always use a leading zero — write '0.5 mg', not '.5 mg'.", Severity.HIGH),
    (r"@", 0, "@ symbol",
     "'@' is misread as the number 2.",
     "Write 'at'.", Severity.LOW),
]

UNSAFE_ABBREVIATIONS: list[tuple[re.Pattern[str], str, str, str, Severity]] = [
    (re.compile(pat, flags), label, reason, safer, sev)
    for pat, flags, label, reason, safer, sev in _ABBR_SPECS
]


# ==========================================================================
# Active-ingredient map (Requirement 2: "duplicate active ingredients")
# --------------------------------------------------------------------------
# Maps a brand or a synonym to its canonical active ingredient(s). Used to catch
# therapeutic duplication — the same ingredient prescribed under two names (e.g.
# "Crocin" and "Dolo" are both paracetamol). Deliberately small and curated;
# unknown names simply fall back to their own normalised name as the key, so the
# validator degrades gracefully and never fabricates a duplicate.
# ==========================================================================
BRAND_TO_INGREDIENT: dict[str, str] = {
    # Paracetamol / acetaminophen family
    "paracetamol": "paracetamol",
    "acetaminophen": "paracetamol",
    "crocin": "paracetamol",
    "dolo": "paracetamol",
    "calpol": "paracetamol",
    "tylenol": "paracetamol",
    "pcm": "paracetamol",
    "metacin": "paracetamol",
    # Ibuprofen
    "ibuprofen": "ibuprofen",
    "brufen": "ibuprofen",
    "advil": "ibuprofen",
    "combiflam": "ibuprofen+paracetamol",
    # Aspirin
    "aspirin": "aspirin",
    "asa": "aspirin",
    "ecosprin": "aspirin",
    "disprin": "aspirin",
    # Diclofenac
    "diclofenac": "diclofenac",
    "voveran": "diclofenac",
    "voltaren": "diclofenac",
    # Amoxicillin / co-amoxiclav
    "amoxicillin": "amoxicillin",
    "amoxil": "amoxicillin",
    "mox": "amoxicillin",
    "augmentin": "amoxicillin+clavulanate",
    "clavam": "amoxicillin+clavulanate",
    # Azithromycin
    "azithromycin": "azithromycin",
    "azithral": "azithromycin",
    "zithromax": "azithromycin",
    # Pantoprazole / omeprazole (PPIs kept distinct)
    "pantoprazole": "pantoprazole",
    "pan": "pantoprazole",
    "pantop": "pantoprazole",
    "omeprazole": "omeprazole",
    "omez": "omeprazole",
    # Metformin
    "metformin": "metformin",
    "glycomet": "metformin",
    "glucophage": "metformin",
    # Atorvastatin
    "atorvastatin": "atorvastatin",
    "atorva": "atorvastatin",
    "lipitor": "atorvastatin",
    # Amlodipine
    "amlodipine": "amlodipine",
    "amlong": "amlodipine",
    "amlokind": "amlodipine",
    # Cetirizine
    "cetirizine": "cetirizine",
    "cetzine": "cetirizine",
    "alerid": "cetirizine",
    # Omeprazole handled above; Cough/others can be added here over time.
}

# Words stripped from a medicine name when normalising it (dosage forms + units).
_FORM_WORDS = {
    "tablet", "tablets", "tab", "tabs", "cap", "caps", "capsule", "capsules",
    "syrup", "syp", "susp", "suspension", "injection", "inj", "drops", "drop",
    "cream", "ointment", "gel", "solution", "soln", "spray", "sachet", "powder",
    "mg", "mcg", "ug", "g", "gm", "ml", "iu", "unit", "units", "sr", "xr", "cr",
    "od", "bd", "tds", "qid", "hs", "prn",
}
_DOSE_TOKEN = re.compile(r"^\d+(?:\.\d+)?(?:mg|mcg|ml|g|gm|iu|%)?$", re.IGNORECASE)
_NON_WORD = re.compile(r"[^a-z0-9\s]")


def normalize_name(name: str | None) -> str:
    """Lower-case a medicine name and strip dosage/form noise for comparison.

    ``"Dolo 650 Tablet"`` and ``"dolo-650 tab"`` both normalise to ``"dolo"`` so
    the duplicate and ingredient checks compare like with like. Returns an empty
    string for empty/None input.
    """
    if not name:
        return ""
    text = _NON_WORD.sub(" ", name.lower())
    tokens = [
        t for t in text.split()
        if t not in _FORM_WORDS and not _DOSE_TOKEN.match(t)
    ]
    return " ".join(tokens).strip()


def active_ingredient(name: str | None) -> str:
    """Resolve a medicine name to its canonical active-ingredient key.

    Falls back to the normalised name itself when the brand is unknown, so the
    grouping is always well-defined and never invents a false match.
    """
    norm = normalize_name(name)
    if not norm:
        return ""
    # Try the whole normalised name, then its first token (brand head).
    if norm in BRAND_TO_INGREDIENT:
        return BRAND_TO_INGREDIENT[norm]
    head = norm.split()[0]
    return BRAND_TO_INGREDIENT.get(head, norm)


# Heuristic "gibberish" detector for OCR'd names that resolved to nothing sane.
_ALPHA = re.compile(r"[a-z]", re.IGNORECASE)


def looks_like_gibberish(text: str | None) -> bool:
    """True when a name is too short or too non-alphabetic to be a real drug."""
    if not text:
        return True
    cleaned = text.strip()
    if len(cleaned) < 3:
        return True
    letters = len(_ALPHA.findall(cleaned))
    # Fewer than half the characters are letters → almost certainly noise.
    return letters < max(3, len(cleaned) * 0.5)
