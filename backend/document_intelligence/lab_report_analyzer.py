"""Structured lab-value extraction + High/Low/Normal analysis.

Runs for the lab-style document types (Blood Test Report, CBC, LFT, KFT,
Lipid Profile, Thyroid). Extracts ``<test name> <value> <unit>? <range>?``
rows with a tolerant regex, resolves each test name against a built-in
reference-range table via fuzzy matching (``rapidfuzz`` — the same library
already used for medicine matching), and grades each result High / Low /
Normal against whichever range is available (the report's own stated range
is preferred over the built-in table, since labs vary).
"""

from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz, process

from backend.config import settings
from backend.document_intelligence.schemas import LabReportAnalysis, LabTestResult

logger = logging.getLogger("document_intelligence")

# --------------------------------------------------------------------------
# Built-in reference ranges: canonical name -> (unit, low, high, aliases)
# Adult, non-pregnant reference ranges (approximate, for decision-support
# only — the report's own stated range always takes priority when present).
# --------------------------------------------------------------------------
_REFERENCE_TABLE: dict[str, tuple[str, float, float, list[str]]] = {
    # --- CBC ---
    "Hemoglobin": ("g/dL", 13.0, 17.0, ["haemoglobin", "hb", "hgb"]),
    "WBC Count": ("/cumm", 4000, 11000, ["total leucocyte count", "tlc", "wbc", "leucocyte count"]),
    "RBC Count": ("mill/cumm", 4.5, 5.5, ["rbc", "red blood cell count"]),
    "Platelet Count": ("lakhs/cumm", 1.5, 4.5, ["platelets"]),
    "Hematocrit": ("%", 40.0, 50.0, ["haematocrit", "pcv", "packed cell volume"]),
    "MCV": ("fL", 83.0, 101.0, ["mean corpuscular volume"]),
    "MCH": ("pg", 27.0, 32.0, ["mean corpuscular hemoglobin"]),
    "MCHC": ("g/dL", 31.5, 34.5, ["mean corpuscular hemoglobin concentration"]),
    "Neutrophils": ("%", 40.0, 80.0, []),
    "Lymphocytes": ("%", 20.0, 40.0, []),
    "Eosinophils": ("%", 1.0, 6.0, []),
    "Monocytes": ("%", 2.0, 10.0, []),
    "Basophils": ("%", 0.0, 2.0, []),
    # --- LFT ---
    "SGOT": ("U/L", 5.0, 40.0, ["ast", "aspartate aminotransferase"]),
    "SGPT": ("U/L", 5.0, 40.0, ["alt", "alanine aminotransferase"]),
    "Total Bilirubin": ("mg/dL", 0.2, 1.2, ["bilirubin total", "bilirubin"]),
    "Direct Bilirubin": ("mg/dL", 0.0, 0.3, ["bilirubin direct", "conjugated bilirubin"]),
    "Alkaline Phosphatase": ("U/L", 44.0, 147.0, ["alp"]),
    "Total Protein": ("g/dL", 6.0, 8.3, []),
    "Albumin": ("g/dL", 3.5, 5.0, []),
    "Globulin": ("g/dL", 2.0, 3.5, []),
    "GGT": ("U/L", 8.0, 61.0, ["gamma gt", "ggtp"]),
    # --- KFT ---
    "Blood Urea": ("mg/dL", 7.0, 20.0, ["urea"]),
    "Serum Creatinine": ("mg/dL", 0.6, 1.2, ["creatinine"]),
    "Uric Acid": ("mg/dL", 3.4, 7.0, []),
    "eGFR": ("mL/min/1.73m2", 90.0, 120.0, ["gfr"]),
    "Sodium": ("mEq/L", 135.0, 145.0, ["na"]),
    "Potassium": ("mEq/L", 3.5, 5.1, ["k"]),
    "Chloride": ("mEq/L", 96.0, 106.0, ["cl"]),
    # --- Lipid Profile ---
    "Total Cholesterol": ("mg/dL", 0.0, 200.0, ["cholesterol"]),
    "Triglycerides": ("mg/dL", 0.0, 150.0, []),
    "HDL Cholesterol": ("mg/dL", 40.0, 60.0, ["hdl"]),
    "LDL Cholesterol": ("mg/dL", 0.0, 100.0, ["ldl"]),
    "VLDL Cholesterol": ("mg/dL", 5.0, 30.0, ["vldl"]),
    # --- Thyroid ---
    "TSH": ("mIU/L", 0.4, 4.0, ["thyroid stimulating hormone"]),
    "Total T3": ("ng/dL", 80.0, 200.0, ["t3"]),
    "Total T4": ("µg/dL", 5.0, 12.0, ["t4"]),
    "Free T3": ("pg/mL", 2.3, 4.2, ["ft3"]),
    "Free T4": ("ng/dL", 0.8, 1.8, ["ft4"]),
}

# Flat alias -> canonical name lookup for fuzzy matching.
_ALIAS_INDEX: dict[str, str] = {}
for _canonical, (_unit, _low, _high, _aliases) in _REFERENCE_TABLE.items():
    _ALIAS_INDEX[_canonical.lower()] = _canonical
    for _alias in _aliases:
        _ALIAS_INDEX[_alias.lower()] = _canonical

_ROW_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ./%()+-]{2,45}?)\s*[:\-]?\s*"
    r"(?P<value>\d{1,6}(?:[.,]\d{1,3})?)\s*"
    r"(?P<unit>%|[a-zA-Zµμ]{1,6}(?:/[a-zA-Zµμ0-9.]{1,10})?)?\s*"
    r"(?:[\[(]?\s*(?P<range_low>\d{1,5}(?:\.\d{1,3})?)\s*[-–to]{1,4}\s*"
    r"(?P<range_high>\d{1,5}(?:\.\d{1,3})?)\s*[\])]?)?"
)

_MATCH_SCORE_CUTOFF = settings.DOCUMENT_LAB_MATCH_THRESHOLD


def _resolve_reference(name: str) -> tuple[str | None, str | None, float | None, float | None]:
    """Fuzzy-match ``name`` to the built-in table. Returns (canonical, unit, low, high)."""
    if not _ALIAS_INDEX:
        return None, None, None, None
    match = process.extractOne(
        name.lower(), _ALIAS_INDEX.keys(), scorer=fuzz.WRatio, score_cutoff=_MATCH_SCORE_CUTOFF
    )
    if not match:
        return None, None, None, None
    alias, _score, _idx = match
    canonical = _ALIAS_INDEX[alias]
    unit, low, high, _ = _REFERENCE_TABLE[canonical]
    return canonical, unit, low, high


def _status(value: float, low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "unknown"
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "normal"


def extract_lab_rows(raw_text: str) -> list[LabTestResult]:
    """Best-effort extraction of test rows from OCR'd/parsed lab-report text."""
    rows: list[LabTestResult] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if len(line) < 4 or not any(c.isdigit() for c in line):
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip(" .:-")
        if len(name) < 3 or not any(c.isalpha() for c in name):
            continue
        try:
            value = float(m.group("value").replace(",", ""))
        except (TypeError, ValueError):
            continue

        canonical, ref_unit, ref_low, ref_high = _resolve_reference(name)
        display_name = canonical or name.title()
        unit = (m.group("unit") or ref_unit or "").strip() or None

        # A range stated on the report line itself wins over the built-in table.
        low = ref_low
        high = ref_high
        reference_range: str | None = None
        if m.group("range_low") and m.group("range_high"):
            low = float(m.group("range_low"))
            high = float(m.group("range_high"))
            reference_range = f"{m.group('range_low')} - {m.group('range_high')}"
        elif ref_low is not None and ref_high is not None:
            reference_range = f"{ref_low} - {ref_high}"

        rows.append(
            LabTestResult(
                test_name=display_name,
                value=value,
                unit=unit,
                reference_range=reference_range,
                ref_low=low,
                ref_high=high,
                status=_status(value, low, high),
                raw_line=line,
            )
        )
    return rows


def analyze(raw_text: str) -> LabReportAnalysis:
    """Extract + grade every test row found in ``raw_text``."""
    try:
        results = extract_lab_rows(raw_text)
    except Exception:  # noqa: BLE001 — extraction must never crash the pipeline
        logger.exception("Lab row extraction failed; returning empty analysis")
        results = []
    abnormal = sum(1 for r in results if r.status in {"high", "low"})
    return LabReportAnalysis(results=results, abnormal_count=abnormal, total_count=len(results))
