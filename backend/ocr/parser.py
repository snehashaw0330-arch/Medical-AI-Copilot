"""Extract structured prescription fields from raw OCR text.

Regex/keyword-based field extraction for the non-medicine parts of a script
(doctor, patient, vitals, advice, etc.). Medicine rows are handled by the
medicine-intelligence + field-extraction layers in the pipeline; this module
fills in the surrounding context to build the rich JSON output.

It is deliberately conservative: a field is only returned when a clear cue is
present, so we never fabricate a patient name or diagnosis.
"""

from __future__ import annotations

import re

_DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4})\b",
    re.IGNORECASE,
)
_AGE_RE = re.compile(r"\b(?:age|aged)\s*[:\-]?\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:yrs?|years?|y/o|yo)\b", re.IGNORECASE)
_GENDER_RE = re.compile(r"\b(male|female|m/f|f/m)\b|\b(?:sex|gender)\s*[:\-]?\s*([mf])\b", re.IGNORECASE)
# Require an explicit BP cue so we don't mistake a date (12/05) for blood pressure.
_BP_RE = re.compile(r"\bb\.?\s*p\.?\s*[:\-]?\s*(\d{2,3}\s*/\s*\d{2,3})\s*(?:mmhg)?\b", re.IGNORECASE)
_TEMP_RE = re.compile(r"\b(?:temp|temperature|t)\s*[:\-]?\s*(\d{2,3}(?:\.\d)?)\s*°?\s*([cf])?\b", re.IGNORECASE)
_PULSE_RE = re.compile(r"\b(?:pulse|hr|heart rate)\s*[:\-]?\s*(\d{2,3})\b", re.IGNORECASE)
_WEIGHT_RE = re.compile(r"\b(?:wt|weight)\s*[:\-]?\s*(\d{1,3}(?:\.\d)?)\s*(?:kg)?\b", re.IGNORECASE)
_SPO2_RE = re.compile(r"\b(?:spo2|sao2|o2)\s*[:\-]?\s*(\d{2,3})\s*%?\b", re.IGNORECASE)

# Section header -> field name. Name-like captures stay on one line ([^\n]) and
# are trimmed at the next field label; rest-of-line captures grab to EOL.
_NAME = r"([A-Za-z][A-Za-z. ]{1,40})"
_REST = r"([^\n]+)"
_LABELLED = {
    "doctor": re.compile(rf"\b(?:dr\.?|doctor)\s*[:.\-]?\s*{_NAME}", re.IGNORECASE),
    "patient": re.compile(rf"\b(?:patient|name|pt)\s*[:\-]\s*{_NAME}", re.IGNORECASE),
    "diagnosis": re.compile(rf"\b(?:diagnosis|dx|c/o|complaints?|impression)\s*[:\-]\s*{_REST}", re.IGNORECASE),
    "advice": re.compile(rf"\b(?:advice|advise|instructions?)\s*[:\-]\s*{_REST}", re.IGNORECASE),
    "follow_up": re.compile(rf"\b(?:follow[ \t\-]?up|review|revisit|next visit)\s*[:\-]?\s*{_REST}", re.IGNORECASE),
    "investigations": re.compile(rf"\b(?:investigations?|tests?|lab|labs)\s*[:\-]\s*{_REST}", re.IGNORECASE),
}
_HOSPITAL_RE = re.compile(
    r"^[^\n]*\b(hospital|clinic|nursing home|medical centre|medical center|healthcare|polyclinic)\b[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
# Stop a name capture at the next inline label so "John Doe  Age: 45" -> "John Doe".
_NAME_STOP = re.compile(r"\b(age|aged|sex|gender|date|dob|m/f|f/m|years?|yrs?)\b", re.IGNORECASE)


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"[ \t]+", " ", s).strip(" :-.,")
    return s or None


def _clean_name(s: str | None) -> str | None:
    s = _clean(s)
    if not s:
        return None
    s = _NAME_STOP.split(s, maxsplit=1)[0]  # cut at the next label keyword
    return _clean(s)


def parse_fields(full_text: str, lines: list[str] | None = None) -> dict:
    text = full_text or ""
    out: dict = {
        "doctor": None,
        "hospital": None,
        "patient": None,
        "age": None,
        "gender": None,
        "date": None,
        "diagnosis": None,
        "advice": None,
        "follow_up": None,
        "investigations": None,
        "vitals": {},
    }

    for field, rx in _LABELLED.items():
        m = rx.search(text)
        if m:
            value = _clean_name(m.group(1)) if field in {"doctor", "patient"} else _clean(m.group(1))
            out[field] = value

    if (m := _HOSPITAL_RE.search(text)):
        out["hospital"] = _clean(m.group(0))

    if (m := _DATE_RE.search(text)):
        out["date"] = m.group(1)

    if (m := _AGE_RE.search(text)):
        out["age"] = m.group(1) or m.group(2)

    if (m := _GENDER_RE.search(text)):
        g = (m.group(1) or m.group(2) or "").lower()
        out["gender"] = {"m": "Male", "f": "Female", "male": "Male", "female": "Female"}.get(g)

    vitals = out["vitals"]
    if (m := _BP_RE.search(text)):
        vitals["blood_pressure"] = re.sub(r"\s*/\s*", "/", m.group(1)) + " mmHg"
    if (m := _TEMP_RE.search(text)):
        unit = (m.group(2) or "F").upper()
        vitals["temperature"] = f"{m.group(1)}°{unit}"
    if (m := _PULSE_RE.search(text)):
        vitals["pulse"] = f"{m.group(1)} bpm"
    if (m := _WEIGHT_RE.search(text)):
        vitals["weight"] = f"{m.group(1)} kg"
    if (m := _SPO2_RE.search(text)):
        vitals["spo2"] = f"{m.group(1)}%"

    return out
