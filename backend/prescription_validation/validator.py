"""The deterministic prescription validator (pure, synchronous, auditable).

Given the medicines and text an OCR analysis produced, :func:`validate` runs
every safety check (Requirement 2), scores the prescription 0..100
(Requirement 3), grades it Safe / Needs Review / High Risk (Requirement 4) and
attaches a plain-language reason + fix to every finding (Requirement 5).

No I/O, no async, no framework types beyond the request/report schemas — so the
whole thing is trivially unit-testable and the service layer only has to worry
about orchestration and persistence.
"""

from __future__ import annotations

from collections import defaultdict

from backend.prescription_validation import rules
from backend.prescription_validation.schemas import (
    DuplicateGroup,
    IssueCategory,
    MedicineInput,
    RiskLevel,
    Severity,
    ValidationIssue,
    ValidationReport,
)

# Categories whose issues the UI renders in the "Prescription Warnings" panel
# (everything that is neither a duplicate nor a missing-field issue).
_WARNING_CATEGORIES = {
    IssueCategory.UNSAFE_ABBREVIATION,
    IssueCategory.SUSPICIOUS_NAME,
    IssueCategory.LOW_CONFIDENCE,
    IssueCategory.PRESCRIPTION_ERROR,
}


def _display_name(med: MedicineInput) -> str:
    """Best human-readable label for a medicine row."""
    return (med.name or med.raw_text or "unknown medicine").strip()


# ==========================================================================
# Individual checks — each returns a list of ValidationIssue.
# ==========================================================================
def _check_duplicates(
    medicines: list[MedicineInput],
) -> tuple[list[ValidationIssue], list[DuplicateGroup]]:
    """Flag the same drug (Requirement 2a) and same active ingredient (2b)."""
    issues: list[ValidationIssue] = []
    groups: list[DuplicateGroup] = []

    # 2a) Exact duplicate medicines — group by normalised name.
    by_name: dict[str, list[str]] = defaultdict(list)
    for med in medicines:
        norm = rules.normalize_name(med.name or med.raw_text)
        if norm:
            by_name[norm].append(_display_name(med))
    duplicated_names: set[str] = set()
    for norm, names in by_name.items():
        if len(names) < 2:
            continue
        duplicated_names.add(norm)
        groups.append(DuplicateGroup(kind="medicine", value=names[0], medicines=names))
        issues.append(ValidationIssue(
            code="duplicate_medicine",
            category=IssueCategory.DUPLICATE_MEDICINE,
            severity=Severity.HIGH,
            title="Duplicate medicine",
            detail=f"'{names[0]}' appears {len(names)} times on this prescription.",
            recommendation="Confirm this is intentional — repeating the same drug "
                           "risks accidental double-dosing. Remove the duplicate "
                           "or clarify the schedule.",
            medicine=names[0],
        ))

    # 2b) Same active ingredient under different names (therapeutic duplication).
    by_ingredient: dict[str, list[str]] = defaultdict(list)
    ingredient_norms: dict[str, set[str]] = defaultdict(set)
    for med in medicines:
        label = med.name or med.raw_text
        norm = rules.normalize_name(label)
        ing = rules.active_ingredient(label)
        if ing:
            by_ingredient[ing].append(_display_name(med))
            ingredient_norms[ing].add(norm)
    for ing, names in by_ingredient.items():
        # Only interesting when >=2 *distinct* names share an ingredient, and it
        # is not already reported as an exact-name duplicate above.
        distinct = ingredient_norms[ing]
        if len(names) < 2 or len(distinct) < 2:
            continue
        if distinct & duplicated_names and len(distinct) < 2:
            continue
        groups.append(DuplicateGroup(kind="active_ingredient", value=ing, medicines=names))
        issues.append(ValidationIssue(
            code="duplicate_ingredient",
            category=IssueCategory.DUPLICATE_INGREDIENT,
            severity=Severity.HIGH,
            title="Duplicate active ingredient",
            detail=f"{', '.join(names)} all contain '{ing}'.",
            recommendation="These are the same active ingredient under different "
                           "names. Prescribing them together risks a cumulative "
                           "overdose — verify only one is intended.",
            medicine=names[0],
            evidence=ing,
        ))

    return issues, groups


def _check_missing_fields(medicines: list[MedicineInput]) -> list[ValidationIssue]:
    """Flag missing dosage / frequency / duration (Requirement 2c-e)."""
    issues: list[ValidationIssue] = []
    for med in medicines:
        name = _display_name(med)
        has_freq = bool((med.frequency or "").strip() or (med.frequency_expanded or "").strip())
        if not (med.dosage or "").strip():
            issues.append(ValidationIssue(
                code="missing_dosage", category=IssueCategory.MISSING_INFO,
                severity=Severity.MEDIUM, title="Missing dosage",
                detail=f"No dosage (strength/amount) was found for '{name}'.",
                recommendation="A dosage is required to dispense safely. Confirm "
                               "the strength (e.g. 500 mg) from the prescription.",
                medicine=name))
        if not has_freq:
            issues.append(ValidationIssue(
                code="missing_frequency", category=IssueCategory.MISSING_INFO,
                severity=Severity.MEDIUM, title="Missing frequency",
                detail=f"No dosing frequency was found for '{name}'.",
                recommendation="Confirm how often to take it (e.g. twice daily) — "
                               "an unspecified frequency risks under- or overdosing.",
                medicine=name))
        if not (med.duration or "").strip():
            issues.append(ValidationIssue(
                code="missing_duration", category=IssueCategory.MISSING_INFO,
                severity=Severity.LOW, title="Missing duration",
                detail=f"No treatment duration was found for '{name}'.",
                recommendation="Confirm how many days to continue — important for "
                               "antibiotics and short courses in particular.",
                medicine=name))
    return issues


def _check_unsafe_abbreviations(text: str) -> list[ValidationIssue]:
    """Scan the full prescription text for error-prone abbreviations (2f)."""
    issues: list[ValidationIssue] = []
    if not text:
        return issues
    seen: set[str] = set()
    for pattern, label, reason, safer, severity in rules.UNSAFE_ABBREVIATIONS:
        match = pattern.search(text)
        if not match or label in seen:
            continue
        seen.add(label)
        issues.append(ValidationIssue(
            code="unsafe_abbreviation", category=IssueCategory.UNSAFE_ABBREVIATION,
            severity=severity, title=f"Unsafe abbreviation: {label}",
            detail=reason, recommendation=safer,
            evidence=match.group(0)))
    return issues


def _check_suspicious_names(
    medicines: list[MedicineInput], low_confidence: float,
) -> list[ValidationIssue]:
    """Flag unrecognised / gibberish / weakly-matched names (2g) and low
    OCR confidence rows (2h)."""
    issues: list[ValidationIssue] = []
    for med in medicines:
        name = _display_name(med)
        top_score = med.candidates[0].get("score", 0.0) if med.candidates else None

        # 2g) Suspicious / unrecognised medicine name.
        if not med.name and rules.looks_like_gibberish(med.raw_text):
            issues.append(ValidationIssue(
                code="unrecognized_name", category=IssueCategory.SUSPICIOUS_NAME,
                severity=Severity.MEDIUM, title="Unrecognised medicine name",
                detail=f"'{name}' could not be matched to any known medicine and "
                       "does not look like a valid drug name.",
                recommendation="Re-read this line on the original prescription; "
                               "the name may have been misread by OCR.",
                medicine=name, evidence=med.raw_text or None))
        elif med.needs_review or (top_score is not None and top_score <= rules.WEAK_MATCH_SCORE):
            issues.append(ValidationIssue(
                code="weak_match", category=IssueCategory.SUSPICIOUS_NAME,
                severity=Severity.MEDIUM, title="Uncertain medicine match",
                detail=f"'{name}' was matched with low confidence"
                       + (f" ({top_score:.0f}%)" if top_score is not None else "")
                       + " — it may be the wrong medicine.",
                recommendation="Verify this medicine against the original "
                               "prescription before relying on it.",
                medicine=name))

        # 2h) Low OCR confidence for the row overall.
        if med.confidence < low_confidence:
            issues.append(ValidationIssue(
                code="low_confidence", category=IssueCategory.LOW_CONFIDENCE,
                severity=Severity.LOW if med.confidence >= low_confidence * 0.75 else Severity.MEDIUM,
                title="Low OCR confidence",
                detail=f"'{name}' was read with {med.confidence * 100:.0f}% "
                       "confidence by the OCR engine.",
                recommendation="Low-confidence rows are the most likely to be "
                               "wrong — double-check the name, dose and schedule.",
                medicine=name))
    return issues


def _check_prescription_errors(medicines: list[MedicineInput]) -> list[ValidationIssue]:
    """Composite red flags a single-field check would miss (2i)."""
    issues: list[ValidationIssue] = []
    for med in medicines:
        name = _display_name(med)
        has_freq = bool((med.frequency or "").strip() or (med.frequency_expanded or "").strip())
        # A row with neither dose nor frequency nor duration is essentially
        # uninterpretable — escalate beyond the individual missing-field flags.
        if not (med.dosage or "").strip() and not has_freq and not (med.duration or "").strip():
            issues.append(ValidationIssue(
                code="incomplete_order", category=IssueCategory.PRESCRIPTION_ERROR,
                severity=Severity.HIGH, title="Incomplete medication order",
                detail=f"'{name}' has no dosage, frequency or duration — it cannot "
                       "be dispensed safely as written.",
                recommendation="Treat this as an incomplete order and confirm the "
                               "full dosing instructions with the prescriber.",
                medicine=name))
    return issues


# ==========================================================================
# Scoring + grading (Requirements 3 & 4)
# ==========================================================================
def _score(issues: list[ValidationIssue]) -> float:
    """Subtract severity-weighted penalties from a perfect 100 (clamped)."""
    penalty = sum(rules.SEVERITY_PENALTY[i.severity] for i in issues)
    return round(max(0.0, 100.0 - penalty), 1)


def _grade(score: float, issues: list[ValidationIssue]) -> RiskLevel:
    """Map the score + worst severity onto the three-level risk scale."""
    severities = {i.severity for i in issues}
    if Severity.HIGH in severities or score < rules.HIGH_RISK_SCORE_CEILING:
        return RiskLevel.HIGH_RISK
    if Severity.MEDIUM in severities or score < rules.SAFE_SCORE_FLOOR:
        return RiskLevel.NEEDS_REVIEW
    return RiskLevel.SAFE


def _summarize(
    risk: RiskLevel, score: float, medicine_count: int, issues: list[ValidationIssue],
) -> str:
    """One-line human summary for the report header."""
    if not issues:
        return (f"No issues found across {medicine_count} medicine(s). "
                f"Validation score {score:.0f}/100.")
    highs = sum(1 for i in issues if i.severity == Severity.HIGH)
    lead = {
        RiskLevel.HIGH_RISK: "High risk",
        RiskLevel.NEEDS_REVIEW: "Needs review",
        RiskLevel.SAFE: "Generally safe",
    }[risk]
    high_note = f", including {highs} critical issue(s)" if highs else ""
    return (f"{lead}: {len(issues)} issue(s) found{high_note} across "
            f"{medicine_count} medicine(s). Validation score {score:.0f}/100.")


# ==========================================================================
# Public entry point
# ==========================================================================
def validate(
    medicines: list[MedicineInput],
    raw_text: str = "",
    fields: dict | None = None,
    *,
    low_confidence: float = rules.DEFAULT_LOW_CONFIDENCE,
) -> ValidationReport:
    """Run every safety check and assemble a full :class:`ValidationReport`."""
    # Build the text scanned for unsafe abbreviations: the raw OCR text plus each
    # medicine's own instruction/schedule fields and any free-text advice.
    parts: list[str] = [raw_text or ""]
    for med in medicines:
        parts.extend(filter(None, [
            med.instructions, med.frequency, med.dosage, med.duration, med.raw_text,
        ]))
    if fields:
        parts.extend(str(v) for v in fields.values() if isinstance(v, str))
    scan_text = "\n".join(p for p in parts if p)

    # Run each check.
    dup_issues, dup_groups = _check_duplicates(medicines)
    issues: list[ValidationIssue] = []
    issues.extend(dup_issues)
    issues.extend(_check_missing_fields(medicines))
    issues.extend(_check_unsafe_abbreviations(scan_text))
    issues.extend(_check_suspicious_names(medicines, low_confidence))
    issues.extend(_check_prescription_errors(medicines))

    # Sort most-severe first for a stable, useful display order.
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    issues.sort(key=lambda i: order[i.severity])

    score = _score(issues)
    risk = _grade(score, issues)
    counts = {
        s.value: sum(1 for i in issues if i.severity == s) for s in Severity
    }

    missing = [i for i in issues if i.category == IssueCategory.MISSING_INFO]
    warnings = [i for i in issues if i.category in _WARNING_CATEGORIES]
    # Suggested corrections: de-duplicated recommendations, most-severe first.
    corrections: list[str] = []
    for i in issues:
        if i.recommendation and i.recommendation not in corrections:
            corrections.append(i.recommendation)

    return ValidationReport(
        validation_score=score,
        risk_level=risk,
        summary=_summarize(risk, score, len(medicines), issues),
        medicine_count=len(medicines),
        issues=issues,
        issue_counts=counts,
        missing_information=missing,
        duplicate_medicines=dup_groups,
        warnings=warnings,
        suggested_corrections=corrections,
    )
