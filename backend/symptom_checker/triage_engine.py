"""The deterministic triage engine (pure, synchronous, auditable).

Given the resolved symptoms (with their body-system categories), the user's
1–10 severity, the reported duration and the disease-prediction result, this
module derives everything on the triage side of the assessment:

* red-flag symptoms + an emergency warning (Requirement 4),
* an overall severity level and a 0–100 triage score,
* the four-level urgency grade (Requirement 5),
* a recommended specialist, tests and home-care suggestions (Requirement 4).

It is intentionally free of I/O, async and framework types so the whole triage
policy is readable and unit-testable in one place. The service layer supplies
the disease predictions and RAG evidence; this engine turns everything into an
actionable, safety-first recommendation.
"""

from __future__ import annotations

from backend.symptom_checker.schemas import (
    ConditionHypothesis,
    RedFlag,
    SeverityLevel,
    UrgencyLevel,
)
from backend.symptom_checker.symptom_matcher import normalize

# ==========================================================================
# Red-flag symptoms (Requirement 4). Canonical name → (reason, is_emergency).
# An emergency red flag forces an EMERGENCY grade regardless of the score.
# ==========================================================================
RED_FLAGS: dict[str, tuple[str, bool]] = {
    "chest pain": ("Chest pain can be a sign of a heart attack or other serious "
                   "cardiac or lung problem.", True),
    "breathlessness": ("Severe difficulty breathing can be life-threatening.", True),
    "shortness of breath": ("Severe difficulty breathing can be life-threatening.", True),
    "slurred speech": ("Sudden slurred speech is a classic warning sign of a stroke.", True),
    "altered sensorium": ("A change in alertness or consciousness needs emergency "
                          "assessment.", True),
    "unconsciousness": ("Loss of consciousness is a medical emergency.", True),
    "loss of balance": ("Sudden loss of balance or coordination may indicate a stroke.", True),
    "seizure": ("An active or first-time seizure is a medical emergency.", True),
    "stomach bleeding": ("Gastrointestinal bleeding can cause dangerous blood loss.", True),
    "bloody stool": ("Blood in the stool can indicate serious internal bleeding.", True),
    "blood in sputum": ("Coughing up blood needs urgent evaluation.", True),
    "blood in urine": ("Visible blood in the urine should be assessed promptly.", False),
    "suicidal thoughts": ("Thoughts of self-harm require immediate support — please "
                          "reach out to a crisis line or emergency services now.", True),
    "stiff neck": ("A stiff neck together with fever can indicate meningitis.", False),
    "fainting": ("Fainting can point to a heart-rhythm or blood-pressure problem.", False),
    "high fever": ("A persistently high fever may need urgent treatment.", False),
    "dehydration": ("Significant dehydration can require medical fluids.", False),
    "yellowing of eyes": ("Yellowing of the eyes/skin can indicate a liver problem.", False),
}

# ==========================================================================
# Specialist routing (Requirement 4). Dominant symptom category → specialist.
# ==========================================================================
CATEGORY_SPECIALIST: dict[str, str] = {
    "general": "General Physician",
    "respiratory": "Pulmonologist",
    "cardiovascular": "Cardiologist",
    "neurological": "Neurologist",
    "gastrointestinal": "Gastroenterologist",
    "musculoskeletal": "Orthopedic Specialist",
    "skin": "Dermatologist",
    "urinary": "Urologist",
    "mental_health": "Psychiatrist / Mental-Health Professional",
}

# A few disease-name → specialist overrides refine the category default when the
# model is confident about a specific condition. Matched on a lower-case substring.
DISEASE_SPECIALIST: list[tuple[str, str]] = [
    ("heart", "Cardiologist"),
    ("hypertension", "Cardiologist"),
    ("diabetes", "Endocrinologist"),
    ("thyroid", "Endocrinologist"),
    ("hepatitis", "Hepatologist / Gastroenterologist"),
    ("jaundice", "Hepatologist / Gastroenterologist"),
    ("migraine", "Neurologist"),
    ("paralysis", "Neurologist"),
    ("pneumonia", "Pulmonologist"),
    ("tuberculosis", "Pulmonologist"),
    ("asthma", "Pulmonologist"),
    ("arthritis", "Rheumatologist"),
    ("psoriasis", "Dermatologist"),
    ("acne", "Dermatologist"),
    ("urinary", "Urologist"),
    ("kidney", "Nephrologist"),
]

# ==========================================================================
# Recommended tests per category (Requirement 4). A small, sensible default set.
# ==========================================================================
CATEGORY_TESTS: dict[str, list[str]] = {
    "general": ["Complete Blood Count (CBC)", "C-reactive protein (CRP)", "Blood glucose"],
    "respiratory": ["Chest X-ray", "Pulse oximetry (SpO₂)", "Complete Blood Count (CBC)"],
    "cardiovascular": ["Electrocardiogram (ECG)", "Troponin", "Lipid profile", "Blood pressure check"],
    "neurological": ["Neurological examination", "CT / MRI brain (if indicated)", "Blood glucose"],
    "gastrointestinal": ["Complete Blood Count (CBC)", "Liver function test (LFT)", "Stool examination", "Abdominal ultrasound"],
    "musculoskeletal": ["X-ray of the affected joint", "Erythrocyte sedimentation rate (ESR)", "Serum uric acid"],
    "skin": ["Skin examination", "Complete Blood Count (CBC)", "Allergy / patch testing (if recurrent)"],
    "urinary": ["Urinalysis", "Urine culture", "Kidney function test (KFT)"],
    "mental_health": ["Clinical mental-health assessment", "Thyroid function test", "Vitamin B12 / D levels"],
}

# ==========================================================================
# Home-care suggestions per category (Requirement 4), used for lower-urgency
# cases. Always paired with a safety note by the engine when urgency is higher.
# ==========================================================================
CATEGORY_HOME_CARE: dict[str, list[str]] = {
    "general": ["Rest and stay well hydrated", "Monitor your temperature",
                "Eat light, nutritious meals"],
    "respiratory": ["Stay hydrated and rest your voice", "Try steam inhalation for congestion",
                    "Avoid smoke and known irritants"],
    "cardiovascular": ["Avoid strenuous exertion until reviewed", "Limit salt and caffeine",
                       "Monitor your blood pressure if you can"],
    "neurological": ["Rest in a quiet, dark room for headaches", "Stay hydrated",
                     "Avoid driving if you feel dizzy"],
    "gastrointestinal": ["Sip oral rehydration fluids", "Eat bland foods (rice, toast, bananas)",
                         "Avoid oily, spicy food and alcohol"],
    "musculoskeletal": ["Rest the affected area", "Apply ice for acute swelling, heat for stiffness",
                        "Gentle stretching within comfort"],
    "skin": ["Keep the area clean and dry", "Avoid scratching and known irritants",
             "Use a fragrance-free moisturiser"],
    "urinary": ["Drink plenty of water", "Avoid caffeine and alcohol",
                "Do not hold urine for long periods"],
    "mental_health": ["Maintain a regular sleep routine", "Stay connected with people you trust",
                      "Try breathing or relaxation exercises"],
}

# Duration key → chronicity contribution to the triage score (0..15).
DURATION_FACTOR: dict[str, float] = {
    "hours": 2.0,
    "1-3_days": 4.0,
    "4-7_days": 6.0,
    "1-2_weeks": 8.0,
    "2-4_weeks": 11.0,
    "chronic": 14.0,
}

# Urgency presentation (label + guidance) for the four grades.
URGENCY_META: dict[UrgencyLevel, tuple[str, str]] = {
    UrgencyLevel.SELF_CARE: (
        "Self Care",
        "Your symptoms can usually be managed safely at home. Rest, follow the "
        "home-care advice below, and seek care if things get worse."),
    UrgencyLevel.VISIT_CLINIC: (
        "Visit Clinic",
        "Consider booking a routine appointment with a doctor in the next day or "
        "two to have these symptoms assessed."),
    UrgencyLevel.URGENT_CARE: (
        "Urgent Care",
        "These symptoms should be seen soon. Visit an urgent-care centre or a "
        "doctor today rather than waiting."),
    UrgencyLevel.EMERGENCY: (
        "Emergency",
        "These symptoms may indicate a medical emergency. Call your local "
        "emergency number or go to the nearest emergency department now."),
}


# --------------------------------------------------------------------------
# Individual steps
# --------------------------------------------------------------------------
def detect_red_flags(canonical_symptoms: list[str]) -> list[RedFlag]:
    """Return the red-flag symptoms present in the resolved symptom list (4)."""
    flags: list[RedFlag] = []
    seen: set[str] = set()
    for s in canonical_symptoms:
        norm = normalize(s)
        if norm in RED_FLAGS and norm not in seen:
            seen.add(norm)
            reason, emergency = RED_FLAGS[norm]
            flags.append(RedFlag(symptom=norm, reason=reason, emergency=emergency))
    return flags


def dominant_category(categories: list[str | None]) -> str:
    """The most-represented body-system category among matched symptoms."""
    counts: dict[str, int] = {}
    for c in categories:
        if c:
            counts[c] = counts.get(c, 0) + 1
    if not counts:
        return "general"
    # Highest count wins; ties broken by a clinical priority order.
    priority = ["cardiovascular", "neurological", "respiratory", "gastrointestinal",
                "urinary", "musculoskeletal", "skin", "mental_health", "general"]
    best = max(counts.items(), key=lambda kv: (kv[1], -priority.index(kv[0]) if kv[0] in priority else 0))
    return best[0]


def recommend_specialist(category: str, conditions: list[ConditionHypothesis]) -> str:
    """Pick a specialist from the dominant category, refined by a confident disease."""
    if conditions and conditions[0].confidence >= 45.0:
        name = conditions[0].disease.lower()
        for needle, specialist in DISEASE_SPECIALIST:
            if needle in name:
                return specialist
    return CATEGORY_SPECIALIST.get(category, "General Physician")


def compute_triage_score(
    severity: int,
    red_flags: list[RedFlag],
    duration: str | None,
    conditions: list[ConditionHypothesis],
) -> float:
    """Combine the signals into a 0–100 urgency score (higher = more urgent)."""
    # User-reported severity is the backbone (1–10 → 8–80).
    score = severity * 8.0
    # Emergency red flags dominate; non-emergency flags add a moderate amount.
    if any(f.emergency for f in red_flags):
        score += 30.0
    score += min(20.0, 8.0 * sum(1 for f in red_flags if not f.emergency))
    # Longer-lasting symptoms nudge urgency up.
    score += DURATION_FACTOR.get(duration or "", 0.0)
    # A confident serious-sounding prediction adds a little.
    if conditions and conditions[0].confidence >= 60.0:
        score += 5.0
    return round(max(0.0, min(100.0, score)), 1)


def grade_urgency(score: float, red_flags: list[RedFlag]) -> UrgencyLevel:
    """Map the score + red flags onto the four-level urgency scale (5)."""
    if any(f.emergency for f in red_flags) or score >= 80.0:
        return UrgencyLevel.EMERGENCY
    if score >= 58.0:
        return UrgencyLevel.URGENT_CARE
    if score >= 36.0:
        return UrgencyLevel.VISIT_CLINIC
    return UrgencyLevel.SELF_CARE


def grade_severity(severity: int, red_flags: list[RedFlag], score: float) -> SeverityLevel:
    """Overall severity level from the slider, red flags and score."""
    if any(f.emergency for f in red_flags) or severity >= 8 or score >= 70.0:
        return SeverityLevel.SEVERE
    if red_flags or severity >= 5 or score >= 45.0:
        return SeverityLevel.MODERATE
    return SeverityLevel.MILD


def build_home_care(category: str, urgency: UrgencyLevel) -> list[str]:
    """Home-care advice for the dominant category, with an urgency-aware header."""
    base = list(CATEGORY_HOME_CARE.get(category, CATEGORY_HOME_CARE["general"]))
    if urgency == UrgencyLevel.EMERGENCY:
        return ["Do not attempt to manage these symptoms at home — seek emergency "
                "care immediately."]
    if urgency == UrgencyLevel.URGENT_CARE:
        base.insert(0, "While arranging to be seen today, you may: ")
    return base


def build_tests(category: str, conditions: list[ConditionHypothesis]) -> list[str]:
    """Recommended investigations for the dominant category (de-duplicated)."""
    tests = list(CATEGORY_TESTS.get(category, CATEGORY_TESTS["general"]))
    # Always ensure a basic blood panel is offered.
    if not any("Blood Count" in t for t in tests):
        tests.append("Complete Blood Count (CBC)")
    seen: set[str] = set()
    out: list[str] = []
    for t in tests:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def emergency_warning(red_flags: list[RedFlag], urgency: UrgencyLevel) -> str | None:
    """A prominent emergency message when warranted (Requirement 4)."""
    emergencies = [f for f in red_flags if f.emergency]
    if urgency != UrgencyLevel.EMERGENCY and not emergencies:
        return None
    if emergencies:
        reasons = " ".join(f.reason for f in emergencies[:3])
        return ("Seek emergency care immediately. " + reasons +
                " Call your local emergency number now.")
    return ("Your reported severity is very high — seek emergency care immediately "
            "if symptoms are worsening.")
