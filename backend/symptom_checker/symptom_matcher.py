"""The categorized symptom catalog + a fuzzy symptom matcher.

This module owns two pure, dependency-light concerns:

* **The catalog (Requirements 2 & 3).** A curated map of the nine required body-
  system categories to their selectable symptoms, plus a small synonym table so
  everyday phrasings ("short of breath", "tummy ache") resolve to a canonical
  symptom. Canonical names are aligned with the disease-prediction model's
  vocabulary wherever possible so the two subsystems agree.
* **Matching.** :class:`SymptomMatcher` resolves free-text or picked symptoms to
  canonical catalog entries (exact → synonym → fuzzy via RapidFuzz), reports the
  category of each, and powers autocomplete.

No I/O, no async, no framework types — trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

# ==========================================================================
# Categorized catalog (Requirement 3) — the nine required groups.
# Canonical symptom names are lower-case and, where possible, match the
# disease-prediction feature vocabulary so predictions stay consistent.
# ==========================================================================
CATEGORY_LABELS: dict[str, str] = {
    "general": "General",
    "respiratory": "Respiratory",
    "cardiovascular": "Cardiovascular",
    "neurological": "Neurological",
    "gastrointestinal": "Gastrointestinal",
    "musculoskeletal": "Musculoskeletal",
    "skin": "Skin",
    "urinary": "Urinary",
    "mental_health": "Mental Health",
}

CATALOG: dict[str, list[str]] = {
    "general": [
        "fever", "high fever", "mild fever", "chills", "fatigue", "weakness",
        "sweating", "headache", "body ache", "loss of appetite", "malaise",
        "dizziness", "dehydration", "weight loss", "night sweats",
        "swelled lymph nodes",
    ],
    "respiratory": [
        "cough", "breathlessness", "shortness of breath", "sore throat",
        "throat irritation", "runny nose", "continuous sneezing", "congestion",
        "sinus pressure", "phlegm", "mucoid sputum", "blood in sputum",
        "wheezing", "loss of smell", "chest congestion",
    ],
    "cardiovascular": [
        "chest pain", "palpitations", "fast heart rate", "swollen legs",
        "swollen extremeties", "prominent veins on calf", "cold hands and feets",
        "fainting", "high blood pressure", "irregular heartbeat",
    ],
    "neurological": [
        "headache", "dizziness", "loss of balance", "slurred speech",
        "altered sensorium", "spinning movements", "stiff neck",
        "blurred and distorted vision", "lack of concentration", "seizure",
        "numbness", "memory loss", "unconsciousness", "pain behind the eyes",
        "tingling",
    ],
    "gastrointestinal": [
        "abdominal pain", "stomach pain", "nausea", "vomiting", "diarrhoea",
        "constipation", "indigestion", "acidity", "bloody stool",
        "stomach bleeding", "distention of abdomen", "passage of gases",
        "yellowing of eyes", "belly pain", "loss of appetite",
    ],
    "musculoskeletal": [
        "joint pain", "muscle pain", "back pain", "neck pain", "knee pain",
        "hip joint pain", "swelling joints", "movement stiffness",
        "painful walking", "muscle weakness", "muscle wasting", "cramps",
    ],
    "skin": [
        "skin rash", "itching", "nodal skin eruptions", "skin peeling",
        "blister", "red spots over body", "pus filled pimples", "blackheads",
        "bruising", "yellowish skin", "dischromic patches", "red sore around nose",
    ],
    "urinary": [
        "burning micturition", "bladder discomfort", "foul smell of urine",
        "continuous feel of urine", "dark urine", "polyuria",
        "spotting urination", "blood in urine",
    ],
    "mental_health": [
        "anxiety", "depression", "mood swings", "irritability", "restlessness",
        "lack of concentration", "excessive worry", "insomnia",
        "suicidal thoughts", "panic attacks",
    ],
}

# Everyday synonyms → canonical catalog name. Keeps the matcher forgiving without
# bloating the pickable catalog. Keys are normalised (lower, single-spaced).
SYNONYMS: dict[str, str] = {
    "short of breath": "shortness of breath",
    "difficulty breathing": "shortness of breath",
    "cant breathe": "shortness of breath",
    "trouble breathing": "shortness of breath",
    "temperature": "fever",
    "high temperature": "high fever",
    "tired": "fatigue",
    "tiredness": "fatigue",
    "exhausted": "fatigue",
    "tummy ache": "abdominal pain",
    "stomach ache": "stomach pain",
    "belly ache": "belly pain",
    "throwing up": "vomiting",
    "loose motions": "diarrhoea",
    "loose motion": "diarrhoea",
    "diarrhea": "diarrhoea",
    "runny nose": "runny nose",
    "blocked nose": "congestion",
    "stuffy nose": "congestion",
    "sneezing": "continuous sneezing",
    "sore throat": "sore throat",
    "throat pain": "sore throat",
    "heart racing": "palpitations",
    "heart pounding": "palpitations",
    "rapid heartbeat": "fast heart rate",
    "dizzy": "dizziness",
    "light headed": "dizziness",
    "lightheaded": "dizziness",
    "fainting": "fainting",
    "passed out": "unconsciousness",
    "blackout": "unconsciousness",
    "vertigo": "spinning movements",
    "blurred vision": "blurred and distorted vision",
    "blurry vision": "blurred and distorted vision",
    "rash": "skin rash",
    "itchy skin": "itching",
    "itchiness": "itching",
    "joint ache": "joint pain",
    "muscle ache": "muscle pain",
    "backache": "back pain",
    "peeing a lot": "polyuria",
    "frequent urination": "polyuria",
    "burning pee": "burning micturition",
    "burning urination": "burning micturition",
    "painful urination": "burning micturition",
    "blood in urine": "blood in urine",
    "sad": "depression",
    "low mood": "depression",
    "worried": "excessive worry",
    "cant sleep": "insomnia",
    "trouble sleeping": "insomnia",
    "self harm": "suicidal thoughts",
    "suicidal": "suicidal thoughts",
    "coughing blood": "blood in sputum",
    "yellow skin": "yellowish skin",
    "yellow eyes": "yellowing of eyes",
}

# Duration buckets offered by the frontend selector. The service maps these to a
# chronicity factor used in triage scoring (see triage_engine).
DURATIONS: list[tuple[str, str]] = [
    ("hours", "A few hours"),
    ("1-3_days", "1–3 days"),
    ("4-7_days", "4–7 days"),
    ("1-2_weeks", "1–2 weeks"),
    ("2-4_weeks", "2–4 weeks"),
    ("chronic", "More than a month"),
]

# Fuzzy-match floor (0..100). Below this a token is treated as unmatched (against
# the *catalog*) — the disease model does its own independent matching.
MATCH_THRESHOLD = 82.0


def normalize(text: str | None) -> str:
    """Lower-case, collapse separators/whitespace for stable comparison."""
    if not text:
        return ""
    cleaned = text.lower().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split()).strip()


@dataclass
class MatchResult:
    """Outcome of resolving one input symptom against the catalog."""

    input: str
    matched: str | None
    category: str | None
    score: float
    method: str  # exact | synonym | fuzzy | none


class SymptomMatcher:
    """Resolves symptoms to the catalog and answers category/autocomplete queries."""

    def __init__(self) -> None:
        # Build lookup structures once.
        self._symptom_to_category: dict[str, str] = {}
        self._all: list[str] = []
        for category, symptoms in CATALOG.items():
            for s in symptoms:
                norm = normalize(s)
                # First category wins for a symptom listed in two groups.
                self._symptom_to_category.setdefault(norm, category)
                if norm not in self._all:
                    self._all.append(norm)
        self._norm_synonyms = {normalize(k): normalize(v) for k, v in SYNONYMS.items()}

    # -- public API --------------------------------------------------------
    @property
    def all_symptoms(self) -> list[str]:
        """Every canonical catalog symptom (for autocomplete/suggestions)."""
        return list(self._all)

    def category_of(self, symptom: str) -> str | None:
        """Return the catalog category key for a canonical symptom, if known."""
        return self._symptom_to_category.get(normalize(symptom))

    def match(self, symptom: str) -> MatchResult:
        """Resolve a single symptom (exact → synonym → fuzzy)."""
        norm = normalize(symptom)
        if not norm:
            return MatchResult(symptom, None, None, 0.0, "none")

        # Exact catalog hit.
        if norm in self._symptom_to_category:
            return MatchResult(symptom, norm, self._symptom_to_category[norm], 100.0, "exact")

        # Known synonym → canonical.
        if norm in self._norm_synonyms:
            canon = self._norm_synonyms[norm]
            return MatchResult(symptom, canon, self._symptom_to_category.get(canon), 98.0, "synonym")

        # Fuzzy against the catalog.
        best = process.extractOne(norm, self._all, scorer=fuzz.WRatio)
        if best and best[1] >= MATCH_THRESHOLD:
            canon = best[0]
            return MatchResult(symptom, canon, self._symptom_to_category.get(canon),
                               float(best[1]), "fuzzy")
        return MatchResult(symptom, None, None, float(best[1]) if best else 0.0, "none")

    def match_many(self, symptoms: list[str]) -> list[MatchResult]:
        """Resolve many symptoms, de-duplicating identical inputs."""
        seen: set[str] = set()
        out: list[MatchResult] = []
        for s in symptoms:
            key = normalize(s)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(self.match(s))
        return out

    def suggest(self, query: str, limit: int = 8) -> list[str]:
        """Autocomplete: catalog symptoms whose name contains/fuzzy-matches query."""
        q = normalize(query)
        if not q:
            return []
        contains = [s for s in self._all if q in s]
        if len(contains) >= limit:
            return contains[:limit]
        # Top up with fuzzy matches not already included.
        extra = [
            name for name, score, _ in process.extract(q, self._all, scorer=fuzz.WRatio, limit=limit)
            if score >= 70 and name not in contains
        ]
        return (contains + extra)[:limit]


# Process-wide singleton (the catalog is static).
_MATCHER: SymptomMatcher | None = None


def get_matcher() -> SymptomMatcher:
    global _MATCHER
    if _MATCHER is None:
        _MATCHER = SymptomMatcher()
    return _MATCHER
