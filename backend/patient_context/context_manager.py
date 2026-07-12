"""Pure business rules for Patient Context & Conversation Memory.

No I/O and no LLM/RAG calls live here — only deterministic logic over data
already in hand: deriving a stable patient id, merging lists without
duplicates, deciding when a conversation needs summarizing, building the
compact grounding text handed to the LLM, and projecting ORM rows onto the
Pydantic response shapes.
"""

from __future__ import annotations

import re

from backend.config import settings
from backend.patient_context.models import PatientContextRecord, PatientEventRecord
from backend.patient_context.schemas import (
    PatientContextDetailResponse,
    PatientContextListItem,
    PatientContextProfile,
    PatientEventItem,
)


def slugify(name: str | None) -> str:
    """Stable patient id from a display name ('John Doe' -> 'john-doe').

    Deliberately a byte-for-byte copy of ``backend.digital_twin.service.slugify``
    (not an import) so this module stays self-contained like every other
    backend module, while still guaranteeing identical patient ids for the
    same patient name across both modules.
    """
    s = (name or "").strip().lower()
    if not s:
        return "unknown"
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"


def merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    """Append items from ``incoming`` that aren't already present (case-insensitive)."""
    seen = {e.lower() for e in existing}
    out = list(existing)
    for item in incoming:
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def needs_summary(messages_since_summary: int) -> bool:
    return messages_since_summary >= settings.PATIENT_CONTEXT_SUMMARY_TRIGGER


def build_grounding_snapshot(
    profile: PatientContextRecord,
    recent_events: list[PatientEventRecord],
    *,
    max_events: int = 8,
) -> str:
    """Compact, durable grounding text for LLM prompts — the cross-session
    analogue of ``backend.copilot.memory.patient_snapshot``.
    """
    lines: list[str] = [f"Patient: {profile.patient_name}"]
    if profile.age is not None:
        lines.append(f"Age: {profile.age}")
    if profile.gender:
        lines.append(f"Gender: {profile.gender}")
    if profile.current_medicines:
        lines.append(f"Current medicines: {', '.join(profile.current_medicines)}")
    if profile.known_conditions:
        lines.append(f"Known conditions: {', '.join(profile.known_conditions)}")
    if profile.allergies:
        lines.append(f"Allergies: {', '.join(profile.allergies)}")
    if profile.symptoms:
        lines.append(f"Reported symptoms: {', '.join(profile.symptoms)}")
    if profile.follow_up_recommendations:
        lines.append(f"Open follow-ups: {'; '.join(profile.follow_up_recommendations[:5])}")
    if profile.last_summary:
        lines.append(f"Conversation summary so far: {profile.last_summary}")

    notable = [e for e in recent_events if e.event_type != "chat_message"][:max_events]
    if notable:
        lines.append("Recent history:")
        for e in notable:
            label = e.title or e.event_type.replace("_", " ")
            lines.append(f"- [{e.event_type}] {label}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ORM row -> Pydantic projections
# ---------------------------------------------------------------------------
def project_event(row: PatientEventRecord) -> PatientEventItem:
    return PatientEventItem.model_validate(row)


def project_profile(row: PatientContextRecord) -> PatientContextProfile:
    return PatientContextProfile.model_validate(row)


def project_list_item(row: PatientContextRecord) -> PatientContextListItem:
    return PatientContextListItem.model_validate(row)


def assemble_detail(
    profile: PatientContextRecord,
    events_by_type: dict[str, list[PatientEventRecord]],
) -> PatientContextDetailResponse:
    """Build the full detail bundle from a profile row + grouped event rows."""

    def items(event_type: str) -> list[PatientEventItem]:
        return [project_event(r) for r in events_by_type.get(event_type, [])]

    return PatientContextDetailResponse(
        profile=project_profile(profile),
        conversation=items("chat_message"),
        ocr_history=items("ocr"),
        medicine_timeline=items("medicine"),
        disease_timeline=items("disease_prediction"),
        interaction_history=items("interaction"),
        reports=items("report"),
        ai_summaries=items("summary"),
        follow_ups=items("follow_up"),
    )
