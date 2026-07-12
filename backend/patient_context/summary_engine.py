"""LLM-backed conversation summarization for Patient Context (offline-safe).

The only file in this module that talks to an LLM. Uses the project's
provider-agnostic layer (:func:`backend.llm.get_llm`), which is offline-safe:
with no cloud/local provider configured it transparently falls back to a
deterministic offline writer, so this always returns something useful and
never raises — the same contract as ``backend.copilot.summary``.

The summarizer is explicitly instructed to preserve medically important
facts (medications, diagnoses, allergies, follow-ups) rather than losing
them when a long conversation is condensed.
"""

from __future__ import annotations

import logging

from backend.config import settings
from backend.patient_context.models import PatientEventRecord

logger = logging.getLogger("patient_context.summary_engine")

_SYSTEM = (
    "You are a careful clinical documentation assistant. Condense a patient "
    "conversation into a short running summary. ALWAYS preserve mentions of "
    "medications, diagnoses/conditions, allergies, symptoms and follow-up "
    "actions — never drop or invent a clinical fact. Be concise and neutral."
)


def _llm():
    if not settings.COPILOT_USE_LLM:
        return None
    try:
        from backend.llm import get_llm

        return get_llm()
    except Exception as exc:  # noqa: BLE001 — offline fallback below
        logger.debug("LLM unavailable for summarization, using offline writer: %s", exc)
        return None


def _format_messages(messages: list[PatientEventRecord]) -> str:
    lines = []
    for m in messages:
        speaker = "Patient/Clinician" if m.role == "user" else "Assistant"
        lines.append(f"{speaker}: {m.text}")
    return "\n".join(lines)


class SummaryEngine:
    """Summarizes a patient's accumulated conversation, offline-safe."""

    async def summarize_conversation(
        self,
        existing_summary: str,
        recent_messages: list[PatientEventRecord],
    ) -> tuple[str, str]:
        """Return ``(summary_text, provider)``."""
        if not recent_messages:
            return existing_summary, "unchanged"

        transcript = _format_messages(recent_messages)
        llm = _llm()
        if llm and llm.available():
            try:
                prompt = (
                    f"Existing summary so far:\n{existing_summary or '(none yet)'}\n\n"
                    f"New conversation to fold in:\n{transcript}\n\n"
                    "Write an updated running summary (4-8 sentences) that merges the "
                    "existing summary with the new conversation, preserving every "
                    "medication, diagnosis, allergy, symptom and follow-up mentioned."
                )
                resp = await llm.acomplete(
                    system=_SYSTEM, prompt=prompt, temperature=0.2, max_tokens=400,
                )
                return resp.text.strip(), resp.provider
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM summarization failed, using offline writer: %s", exc)

        return self._offline_summarize(existing_summary, recent_messages), "offline"

    def _offline_summarize(
        self, existing_summary: str, recent_messages: list[PatientEventRecord],
    ) -> str:
        """Deterministic, extractive fallback — never raises."""
        topics: list[str] = []
        for m in recent_messages:
            snippet = m.text.strip().replace("\n", " ")
            if snippet:
                topics.append(snippet[:140])
        recent_bit = " ".join(topics[-5:])
        if existing_summary:
            return f"{existing_summary} Recently discussed: {recent_bit}".strip()
        return f"Conversation so far covered: {recent_bit}".strip()


_ENGINE: SummaryEngine | None = None


def get_engine() -> SummaryEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SummaryEngine()
    return _ENGINE
