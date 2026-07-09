"""Conversation + activity memory for a Copilot session.

Thin, cohesive helpers that operate on a :class:`~backend.copilot.context.Session`
(defined in ``context.py``) to keep the two mutable, bounded logs the workspace
renders:

* the **conversation** (chat messages), and
* the **AI Activity Timeline** (e.g. ``09:42 OCR Completed``).

Both are capped per session so memory stays bounded, and the module also builds
the compact transcript + patient snapshot that the chat prompt is grounded in.
"""

from __future__ import annotations

from backend.config import settings
from backend.copilot.context import Session
from backend.copilot.schemas import (
    ActivityEvent,
    ChatMessage,
    ChatRole,
    PatientContext,
    StepStatus,
)


def add_message(sess: Session, role: ChatRole, content: str, references: list[str] | None = None) -> ChatMessage:
    """Append a chat message, trimming to the per-session cap."""
    msg = ChatMessage(role=role, content=content, references=references or [])
    sess.messages.append(msg)
    if len(sess.messages) > settings.COPILOT_MAX_MESSAGES:
        del sess.messages[: len(sess.messages) - settings.COPILOT_MAX_MESSAGES]
    return msg


def add_activity(
    sess: Session, label: str, *, detail: str = "",
    status: StepStatus = StepStatus.COMPLETE, step_key: str = "",
) -> ActivityEvent:
    """Append an event to the session-level activity timeline (bounded)."""
    event = ActivityEvent(label=label, detail=detail, status=status, step_key=step_key)
    sess.context.timeline.insert(0, event)
    del sess.context.timeline[settings.COPILOT_MAX_TIMELINE:]
    return event


def recent_messages(sess: Session, limit: int = 10) -> list[ChatMessage]:
    """The last *limit* messages (oldest → newest) for prompt construction."""
    return sess.messages[-limit:]


def transcript(sess: Session, limit: int = 10) -> str:
    """Render the recent conversation as a compact text transcript."""
    lines: list[str] = []
    for m in recent_messages(sess, limit):
        who = {ChatRole.USER: "Clinician", ChatRole.ASSISTANT: "Copilot",
               ChatRole.SYSTEM: "System"}.get(m.role, "?")
        lines.append(f"{who}: {m.content}")
    return "\n".join(lines)


def patient_snapshot(ctx: PatientContext) -> str:
    """A short, factual summary of the remembered patient for grounding chat."""
    parts: list[str] = []
    who = []
    if ctx.patient_name:
        who.append(ctx.patient_name)
    if ctx.age is not None:
        who.append(f"{ctx.age}y")
    if ctx.gender:
        who.append(ctx.gender)
    parts.append("Patient: " + (", ".join(who) if who else "unknown"))
    if ctx.current_medicines:
        parts.append("Current medicines: " + ", ".join(ctx.current_medicines[:12]))
    if ctx.known_conditions:
        parts.append("Known/suspected conditions: " + ", ".join(ctx.known_conditions[:8]))
    if ctx.symptoms:
        parts.append("Reported symptoms: " + ", ".join(ctx.symptoms[:12]))
    if ctx.allergies:
        parts.append("Allergies: " + ", ".join(ctx.allergies[:8]))
    parts.append(f"Analyses this session: {ctx.analysis_count}")
    return "\n".join(parts)
