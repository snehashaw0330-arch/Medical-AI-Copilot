"""Deterministic clinical rules engine — the medical knowledge of the CDSS.

This module is intentionally **pure** (no I/O, no network, no DB) so it is fast,
fully offline, and trivial to unit-test. It takes a :class:`ClinicalContext`
(assembled by the service from OCR medicines, symptoms, patient demographics and
the drug-interaction sub-report) and returns a :class:`RuleFindings` bundle of
red flags, contraindications, possible risks, missing information and suggested
lab tests / next steps.

The knowledge is expressed as small, reviewable data tables rather than buried in
code branches, so a clinician can audit and extend it without reading Python:

* ``RED_FLAG_SYMPTOMS``   — symptom phrases that warrant urgent escalation
* ``DISEASE_LAB_TESTS``   — condition -> recommended work-up
* ``DRUG_MONITORING``     — drug -> monitoring labs while on therapy
* ``PEDIATRIC_CAUTIONS`` / ``ELDERLY_CAUTIONS`` — age-specific drug cautions
* ``PREGNANCY_CAUTION_DRUGS`` — drugs needing pregnancy-status confirmation

Everything here is advisory and must be verified by a clinician; the strings are
written to read as guidance, never as instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.clinical_decision.schemas import RedFlag, RiskLevel


# ==========================================================================
# Context + findings containers
# ==========================================================================
@dataclass
class ClinicalContext:
    """Everything the rules need to reason about one case."""

    age: int | None = None
    gender: str | None = None
    symptoms: list[str] = field(default_factory=list)
    disease: str | None = None
    diagnosis: str | None = None
    medicines: list[str] = field(default_factory=list)          # original names
    resolved_medicines: list[str] = field(default_factory=list)  # canonical
    unmatched_medicines: list[str] = field(default_factory=list)
    # Serialised InteractionReport (may be empty). Used to pull per-drug
    # contraindications / pregnancy / organ warnings into the clinical picture.
    interaction_report: dict[str, Any] = field(default_factory=dict)

    # -- convenience -------------------------------------------------------
    def text_blob(self) -> str:
        """Lowercase concatenation of all free-text clinical inputs."""
        parts = list(self.symptoms) + [self.disease or "", self.diagnosis or ""]
        return " ".join(p for p in parts if p).lower()

    def all_drug_names(self) -> list[str]:
        """Canonical names when available, else the original input names."""
        names = self.resolved_medicines or self.medicines
        return [n.lower() for n in names if n]


@dataclass
class RuleFindings:
    """Raw domain findings produced by the rules (composed later downstream)."""

    red_flags: list[RedFlag] = field(default_factory=list)
    possible_risks: list[str] = field(default_factory=list)
    contraindications: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    recommended_lab_tests: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
    follow_up: list[str] = field(default_factory=list)


# ==========================================================================
# Knowledge tables
# ==========================================================================
# Symptom phrase -> (title, detail, severity). Matched as case-insensitive
# substrings against the combined symptom/diagnosis text.
RED_FLAG_SYMPTOMS: list[tuple[str, str, str, RiskLevel]] = [
    ("chest pain", "Chest pain / chest tightness",
     "Possible acute coronary syndrome — needs urgent ECG and cardiac assessment.",
     RiskLevel.CRITICAL),
    ("crushing chest", "Crushing chest pain",
     "Red flag for myocardial infarction. Arrange emergency evaluation.",
     RiskLevel.CRITICAL),
    ("shortness of breath", "Shortness of breath",
     "Acute dyspnoea can indicate cardiac or respiratory emergency.",
     RiskLevel.HIGH),
    ("difficulty breathing", "Difficulty breathing",
     "Respiratory distress warrants immediate assessment of airway and oxygenation.",
     RiskLevel.HIGH),
    ("slurred speech", "Slurred speech",
     "Possible stroke (FAST). Time-critical — arrange emergency imaging.",
     RiskLevel.CRITICAL),
    ("face droop", "Facial droop",
     "Possible stroke (FAST). Time-critical — arrange emergency imaging.",
     RiskLevel.CRITICAL),
    ("weakness on one side", "Unilateral weakness",
     "Possible stroke. Arrange urgent neurological evaluation.",
     RiskLevel.CRITICAL),
    ("worst headache", "Sudden 'worst-ever' headache",
     "Thunderclap headache can indicate subarachnoid haemorrhage.",
     RiskLevel.CRITICAL),
    ("severe headache", "Severe headache",
     "Severe / sudden headache needs evaluation to exclude serious causes.",
     RiskLevel.HIGH),
    ("stiff neck", "Neck stiffness with fever",
     "Consider meningitis when combined with fever/photophobia.",
     RiskLevel.HIGH),
    ("blood in stool", "Blood in stool",
     "Possible gastrointestinal bleeding — assess and investigate.",
     RiskLevel.HIGH),
    ("black stool", "Black / tarry stool",
     "Melena suggests upper-GI bleeding — needs prompt evaluation.",
     RiskLevel.HIGH),
    ("vomiting blood", "Haematemesis",
     "Vomiting blood indicates active GI bleeding — urgent care.",
     RiskLevel.CRITICAL),
    ("coughing blood", "Haemoptysis",
     "Coughing blood needs evaluation (infection, PE, malignancy).",
     RiskLevel.HIGH),
    ("suicidal", "Suicidal ideation",
     "Mental-health emergency — arrange immediate psychiatric assessment.",
     RiskLevel.CRITICAL),
    ("loss of consciousness", "Loss of consciousness",
     "Syncope / collapse needs evaluation for cardiac and neurological causes.",
     RiskLevel.HIGH),
    ("seizure", "Seizure",
     "New or prolonged seizure activity warrants urgent assessment.",
     RiskLevel.HIGH),
    ("high fever", "High fever",
     "Persistent high fever needs a source work-up, especially in the very young/old.",
     RiskLevel.MODERATE),
    ("severe abdominal pain", "Severe abdominal pain",
     "Acute abdomen — exclude surgical causes urgently.",
     RiskLevel.HIGH),
    ("vision loss", "Sudden vision loss",
     "Sudden visual loss is an ophthalmic/neurological emergency.",
     RiskLevel.HIGH),
    ("severe allergic", "Severe allergic reaction",
     "Possible anaphylaxis — treat as an emergency.",
     RiskLevel.CRITICAL),
    ("dehydration", "Signs of dehydration",
     "Assess hydration and consider fluid replacement, especially in children/elderly.",
     RiskLevel.MODERATE),
]

# Condition keyword -> recommended baseline work-up.
DISEASE_LAB_TESTS: dict[str, list[str]] = {
    "diabetes": ["HbA1c", "Fasting blood glucose", "Lipid profile",
                 "Serum creatinine / eGFR", "Urine microalbumin"],
    "hypertension": ["Blood pressure monitoring", "Serum electrolytes",
                     "Serum creatinine / eGFR", "ECG", "Lipid profile"],
    "tuberculosis": ["Sputum AFB smear", "CBNAAT / GeneXpert", "Chest X-ray"],
    "anemia": ["Complete blood count (CBC)", "Peripheral smear", "Iron studies",
               "Vitamin B12 / Folate"],
    "thyroid": ["TSH", "Free T4"],
    "hypothyroid": ["TSH", "Free T4"],
    "hyperthyroid": ["TSH", "Free T4", "Free T3"],
    "asthma": ["Spirometry", "Peak expiratory flow"],
    "pneumonia": ["Chest X-ray", "Complete blood count (CBC)", "Sputum culture",
                  "SpO2 / pulse oximetry"],
    "bronchitis": ["Chest X-ray", "Complete blood count (CBC)"],
    "urinary tract infection": ["Urine routine & microscopy", "Urine culture"],
    "uti": ["Urine routine & microscopy", "Urine culture"],
    "hepatitis": ["Liver function tests (LFT)", "Viral hepatitis markers"],
    "liver": ["Liver function tests (LFT)", "Abdominal ultrasound"],
    "kidney": ["Serum creatinine / eGFR", "Urine routine & microscopy",
               "Serum electrolytes"],
    "migraine": ["Clinical diagnosis — imaging only if red-flag features"],
    "dengue": ["CBC with platelet count", "NS1 antigen", "Dengue IgM/IgG serology"],
    "typhoid": ["Blood culture", "Widal test", "Complete blood count (CBC)"],
    "malaria": ["Peripheral smear for MP", "Rapid malaria antigen test", "CBC"],
    "covid": ["RT-PCR / rapid antigen", "CBC", "CRP", "SpO2 / pulse oximetry"],
    "fever": ["Complete blood count (CBC)", "CRP"],
    "infection": ["Complete blood count (CBC)", "CRP"],
    "gastroenteritis": ["Stool routine", "Serum electrolytes"],
    "depression": ["PHQ-9 screening", "TSH (exclude organic cause)"],
    "arthritis": ["ESR / CRP", "Rheumatoid factor", "Serum uric acid"],
    "gout": ["Serum uric acid", "Renal function tests"],
    "copd": ["Spirometry", "Chest X-ray", "SpO2 / pulse oximetry"],
    "stroke": ["Urgent CT / MRI brain", "Blood glucose", "Coagulation profile"],
}

# Canonical drug (substring) -> monitoring labs while on therapy.
DRUG_MONITORING: dict[str, list[str]] = {
    "warfarin": ["INR / prothrombin time"],
    "metformin": ["Serum creatinine / eGFR", "Vitamin B12 (long-term)"],
    "atorvastatin": ["Liver function tests (LFT)", "Creatine kinase (if myalgia)"],
    "simvastatin": ["Liver function tests (LFT)", "Creatine kinase (if myalgia)"],
    "rosuvastatin": ["Liver function tests (LFT)"],
    "lithium": ["Serum lithium level", "Renal function", "Thyroid function"],
    "digoxin": ["Serum digoxin level", "Serum electrolytes"],
    "amiodarone": ["Thyroid function tests", "Liver function tests (LFT)", "Chest X-ray"],
    "methotrexate": ["CBC", "Liver function tests (LFT)", "Renal function"],
    "phenytoin": ["Serum phenytoin level", "Liver function tests (LFT)", "CBC"],
    "carbamazepine": ["Serum drug level", "CBC", "Serum sodium"],
    "valproate": ["Liver function tests (LFT)", "CBC", "Serum ammonia (if symptomatic)"],
    "enalapril": ["Renal function", "Serum potassium"],
    "lisinopril": ["Renal function", "Serum potassium"],
    "ramipril": ["Renal function", "Serum potassium"],
    "losartan": ["Renal function", "Serum potassium"],
    "spironolactone": ["Serum potassium", "Renal function"],
    "furosemide": ["Serum electrolytes", "Renal function"],
    "insulin": ["Capillary blood glucose monitoring"],
    "glimepiride": ["Blood glucose monitoring"],
    "prednisolone": ["Blood glucose", "Blood pressure", "Bone health (long-term)"],
    "ibuprofen": ["Renal function (if prolonged use / elderly)"],
    "diclofenac": ["Renal function (if prolonged use / elderly)"],
}

# Drugs that are inappropriate / high-risk in children (short reason).
PEDIATRIC_CAUTIONS: dict[str, str] = {
    "aspirin": "Aspirin in children/teens with a viral illness risks Reye's syndrome.",
    "codeine": "Codeine is contraindicated in young children (respiratory depression risk).",
    "tetracycline": "Tetracyclines can cause permanent tooth discolouration in children.",
    "doxycycline": "Avoid in children under 8 (tooth discolouration) unless essential.",
    "ciprofloxacin": "Fluoroquinolones are generally avoided in children (cartilage concerns).",
    "promethazine": "Avoid in children under 2 (respiratory depression risk).",
}

# Drugs needing extra caution in the elderly (Beers-criteria style, brief).
ELDERLY_CAUTIONS: dict[str, str] = {
    "diazepam": "Long-acting benzodiazepine — falls/confusion risk in the elderly.",
    "lorazepam": "Benzodiazepine — increased falls/sedation risk in the elderly.",
    "alprazolam": "Benzodiazepine — increased falls/sedation risk in the elderly.",
    "diphenhydramine": "Strongly anticholinergic — confusion/urinary retention risk.",
    "amitriptyline": "Anticholinergic tricyclic — caution in the elderly.",
    "ibuprofen": "NSAID — GI bleed and renal risk higher in the elderly.",
    "diclofenac": "NSAID — cardiovascular/GI/renal risk higher in the elderly.",
    "glibenclamide": "Long-acting sulfonylurea — prolonged hypoglycaemia risk.",
}

# Drugs where pregnancy status should be confirmed before use (brief reason).
PREGNANCY_CAUTION_DRUGS: dict[str, str] = {
    "warfarin": "Teratogenic — avoid in pregnancy.",
    "isotretinoin": "Highly teratogenic — pregnancy must be excluded.",
    "methotrexate": "Teratogenic / abortifacient — contraindicated in pregnancy.",
    "enalapril": "ACE inhibitors are contraindicated in pregnancy.",
    "lisinopril": "ACE inhibitors are contraindicated in pregnancy.",
    "ramipril": "ACE inhibitors are contraindicated in pregnancy.",
    "losartan": "ARBs are contraindicated in pregnancy.",
    "valproate": "High neural-tube-defect risk — avoid in pregnancy.",
    "carbamazepine": "Teratogenic risk — specialist review needed in pregnancy.",
    "phenytoin": "Fetal hydantoin syndrome risk — specialist review needed.",
    "doxycycline": "Tetracyclines are avoided in pregnancy.",
    "ibuprofen": "NSAIDs are avoided, especially in the third trimester.",
}


# ==========================================================================
# Helpers
# ==========================================================================
def _dedupe(items: list[str]) -> list[str]:
    """Order-preserving de-duplication (case-insensitive)."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def _drug_matches(drug_names: list[str], table_key: str) -> bool:
    """True when any analysed drug name contains ``table_key`` as a substring."""
    return any(table_key in name for name in drug_names)


# ==========================================================================
# Individual rule groups
# ==========================================================================
def _symptom_red_flags(ctx: ClinicalContext, out: RuleFindings) -> None:
    blob = ctx.text_blob()
    if not blob:
        return
    for phrase, title, detail, severity in RED_FLAG_SYMPTOMS:
        if phrase in blob:
            out.red_flags.append(
                RedFlag(title=title, detail=detail, severity=severity,
                        category="symptom")
            )


def _age_rules(ctx: ClinicalContext, out: RuleFindings) -> None:
    age, drugs = ctx.age, ctx.all_drug_names()
    if age is None:
        return
    if age < 2:
        out.possible_risks.append(
            "Infant patient — all doses must be weight-based and pediatric-verified."
        )
    if age <= 12:
        for key, reason in PEDIATRIC_CAUTIONS.items():
            if _drug_matches(drugs, key):
                out.red_flags.append(
                    RedFlag(title=f"Pediatric caution: {key.title()}",
                            detail=reason, severity=RiskLevel.HIGH, category="age")
                )
                out.contraindications.append(f"{key.title()} — {reason}")
    if age >= 65:
        for key, reason in ELDERLY_CAUTIONS.items():
            if _drug_matches(drugs, key):
                out.possible_risks.append(f"{key.title()} in an older adult — {reason}")
        out.follow_up.append(
            "Review polypharmacy and fall risk at the next visit (older adult)."
        )


def _pregnancy_rules(ctx: ClinicalContext, out: RuleFindings) -> None:
    gender = (ctx.gender or "").strip().lower()
    if gender != "female":
        return
    childbearing = ctx.age is None or (12 <= (ctx.age or 0) <= 50)
    if not childbearing:
        return
    drugs = ctx.all_drug_names()
    for key, reason in PREGNANCY_CAUTION_DRUGS.items():
        if _drug_matches(drugs, key):
            out.red_flags.append(
                RedFlag(title=f"Pregnancy caution: {key.title()}",
                        detail=f"Confirm pregnancy status before use. {reason}",
                        severity=RiskLevel.HIGH, category="pregnancy")
            )
            out.contraindications.append(f"{key.title()} in pregnancy — {reason}")


def _polypharmacy_rules(ctx: ClinicalContext, out: RuleFindings) -> None:
    n = len({d for d in ctx.all_drug_names()})
    if n >= 5:
        out.possible_risks.append(
            f"Polypharmacy — {n} concurrent medicines increase interaction and "
            "adherence risk. Consider a medication review / deprescribing."
        )
        out.follow_up.append("Schedule a medication reconciliation review.")


def _lab_test_rules(ctx: ClinicalContext, out: RuleFindings) -> None:
    # Condition-driven work-up.
    blob = ctx.text_blob()
    for key, tests in DISEASE_LAB_TESTS.items():
        if key in blob:
            out.recommended_lab_tests.extend(tests)
    # Drug-driven monitoring.
    drugs = ctx.all_drug_names()
    for key, tests in DRUG_MONITORING.items():
        if _drug_matches(drugs, key):
            out.recommended_lab_tests.extend(
                f"{t} (monitoring for {key.title()})" for t in tests
            )


def _interaction_derived_rules(ctx: ClinicalContext, out: RuleFindings) -> None:
    """Pull per-drug warnings from the drug-interaction sub-report.

    The interaction module already resolved food/alcohol/pregnancy/organ and
    contraindication warnings from the dataset + RAG; surface the clinically
    important ones here so they appear in the unified clinical picture.
    """
    report = ctx.interaction_report or {}
    for w in report.get("warnings", []) or []:
        med = (w.get("medicine") or "").strip()
        for item in w.get("contraindications", []) or []:
            out.contraindications.append(f"{med}: {item}" if med else item)
        # Organ-function cautions become possible risks.
        for organ in ("kidney", "liver"):
            for item in w.get(organ, []) or []:
                out.possible_risks.append(f"{med} — {organ}: {item}" if med else item)

    # An overall interaction risk of high/critical is itself a red flag.
    overall = (report.get("overall_risk") or "none").lower()
    if overall in {"high", "critical"}:
        n = len(report.get("interactions", []) or [])
        out.red_flags.append(
            RedFlag(
                title="Significant drug–drug interaction",
                detail=f"{n} interaction(s) detected; highest severity {overall.upper()}. "
                       "Review the drug-interaction report below.",
                severity=RiskLevel.CRITICAL if overall == "critical" else RiskLevel.HIGH,
                category="drug",
            )
        )


def _missing_information_rules(ctx: ClinicalContext, out: RuleFindings) -> None:
    if ctx.age is None:
        out.missing_information.append("Patient age (affects dosing and risk).")
    if not (ctx.gender or "").strip():
        out.missing_information.append("Patient gender (affects pregnancy screening).")
    if not ctx.symptoms:
        out.missing_information.append("Presenting symptoms / complaint.")
    if not (ctx.disease or ctx.diagnosis):
        out.missing_information.append("A working diagnosis or predicted condition.")
    if not ctx.medicines:
        out.missing_information.append("Current medications.")
    if ctx.unmatched_medicines:
        out.missing_information.append(
            "Some medicines could not be identified: "
            + ", ".join(ctx.unmatched_medicines)
            + " — verify the spelling / drug name."
        )


# ==========================================================================
# Public entry point
# ==========================================================================
_RULES = (
    _symptom_red_flags,
    _age_rules,
    _pregnancy_rules,
    _polypharmacy_rules,
    _lab_test_rules,
    _interaction_derived_rules,
    _missing_information_rules,
)


def evaluate(ctx: ClinicalContext) -> RuleFindings:
    """Run every rule group over the context and return de-duplicated findings."""
    out = RuleFindings()
    for rule in _RULES:
        try:
            rule(ctx, out)
        except Exception:  # noqa: BLE001 — one bad rule must not sink the report
            # Rules are pure and defensive, but never let a single rule failure
            # break the whole analysis; the service logs at a higher level.
            continue

    # De-duplicate list fields (red flags de-duplicated by title).
    seen_flags: set[str] = set()
    unique_flags: list[RedFlag] = []
    for f in out.red_flags:
        if f.title.lower() not in seen_flags:
            seen_flags.add(f.title.lower())
            unique_flags.append(f)
    out.red_flags = unique_flags

    out.possible_risks = _dedupe(out.possible_risks)
    out.contraindications = _dedupe(out.contraindications)
    out.missing_information = _dedupe(out.missing_information)
    out.recommended_lab_tests = _dedupe(out.recommended_lab_tests)
    out.recommended_next_steps = _dedupe(out.recommended_next_steps)
    out.follow_up = _dedupe(out.follow_up)
    return out
