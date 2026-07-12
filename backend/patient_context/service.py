"""Top-level service for Patient Context & Conversation Memory (async).

Orchestrates ``memory.py`` (persistence), ``context_manager.py`` (business
rules + projections) and ``summary_engine.py`` (LLM summarization). This is
the only file ``router.py`` and other modules (``backend.copilot.service``)
import from this package.

Design contract, identical to every other module in this codebase: async
everywhere, best-effort where a caller (OCR/copilot/etc.) must never break
because patient memory had a hiccup, strict where the caller is this
module's own CRUD endpoints and a real error should surface.
"""

from __future__ import annotations

import logging

from backend.config import settings
from backend.patient_context import context_manager, memory
from backend.patient_context.models import PatientContextRecord, utcnow
from backend.patient_context.schemas import (
    EventType,
    PatientContextCreateRequest,
    PatientContextDeleteResponse,
    PatientContextDetailResponse,
    PatientContextHistoryResponse,
    PatientContextProfile,
    PatientEventAppendRequest,
    PatientEventItem,
)
from backend.patient_context.summary_engine import get_engine as get_summary_engine

logger = logging.getLogger("patient_context.service")

# Event types that fold their payload into the profile's rollup lists.
_ROLLUP_FIELD_BY_EVENT_TYPE = {
    "medicine": "current_medicines",
    "disease_prediction": "known_conditions",
    "follow_up": "follow_up_recommendations",
}


class PatientContextService:
    """Orchestrator for durable, cross-session patient memory."""

    # -- profile CRUD (strict) ---------------------------------------------
    async def create_context(self, req: PatientContextCreateRequest) -> PatientContextProfile:
        patient_id = context_manager.slugify(req.patient_name)
        row = await memory.upsert_profile(
            patient_id,
            patient_name=req.patient_name,
            age=req.age,
            gender=req.gender.lower() if req.gender else None,
            current_medicines=req.current_medicines or None,
            known_conditions=req.known_conditions or None,
            allergies=req.allergies or None,
            symptoms=req.symptoms or None,
        )
        if req.session_id and req.session_id not in (row.session_ids or []):
            row = await memory.upsert_profile(
                patient_id, session_ids=[*(row.session_ids or []), req.session_id],
            )
        logger.info("Patient context created/updated: %s", patient_id)
        return context_manager.project_profile(row)

    async def get_context(self, patient_id: str) -> PatientContextDetailResponse:
        profile = await memory.get_profile(patient_id)
        if profile is None:
            raise KeyError(patient_id)

        events_by_type: dict[str, list] = {}
        for event_type in (
            "chat_message", "ocr", "medicine", "disease_prediction",
            "interaction", "report", "summary", "follow_up",
        ):
            events_by_type[event_type] = await memory.list_events(
                patient_id, event_type, limit=settings.PATIENT_CONTEXT_EVENTS_PER_TYPE,
                newest_first=True,
            )
        # Conversation reads naturally oldest-first.
        events_by_type["chat_message"] = list(reversed(events_by_type["chat_message"]))
        return context_manager.assemble_detail(profile, events_by_type)

    async def list_contexts(self) -> PatientContextHistoryResponse:
        rows = await memory.list_profiles()
        items = [context_manager.project_list_item(r) for r in rows]
        return PatientContextHistoryResponse(items=items, total=len(items))

    async def delete_context(self, patient_id: str) -> PatientContextDeleteResponse:
        removed = await memory.delete_profile_cascade(patient_id)
        if removed < 0:
            raise KeyError(patient_id)
        return PatientContextDeleteResponse(
            patient_id=patient_id, deleted=True, events_removed=removed,
        )

    # -- events (best-effort append, strict read-back) ----------------------
    async def record_event(
        self, patient_id: str, req: PatientEventAppendRequest,
    ) -> PatientEventItem:
        profile = await memory.get_profile(patient_id)
        if profile is None:
            name = req.patient_name or patient_id
            profile = await memory.upsert_profile(patient_id, patient_name=name)

        row = await memory.add_event(
            patient_id, req.event_type,
            title=req.title, text=req.text, payload=req.payload, role=req.role,
            source_session_id=req.source_session_id, source_ref_id=req.source_ref_id,
        )
        if row is None:
            raise RuntimeError("Failed to record patient context event")

        await self._apply_rollup(profile, req.event_type, req.title, req.payload)
        return context_manager.project_event(row)

    async def _apply_rollup(
        self, profile: PatientContextRecord, event_type: EventType, title: str, payload: dict,
    ) -> None:
        """Best-effort: fold a new event into the profile's rollup fields."""
        try:
            updates: dict = {"event_count": (profile.event_count or 0) + 1}
            field = _ROLLUP_FIELD_BY_EVENT_TYPE.get(event_type)
            if field and title:
                existing = getattr(profile, field) or []
                updates[field] = context_manager.merge_unique(existing, [title])
            await memory.upsert_profile(profile.patient_id, **updates)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to roll up event into profile %s", profile.patient_id)

    # -- chat integration (best-effort, called from backend.copilot) --------
    async def get_grounding_context(self, patient_id: str) -> str | None:
        """Best-effort read of durable memory for prompt grounding.

        Returns ``None`` (never raises) if the patient has no memory yet or
        the store is unavailable, so callers can degrade gracefully.
        """
        try:
            profile = await memory.get_profile(patient_id)
            if profile is None:
                return None
            recent = await memory.list_events(patient_id, limit=8, newest_first=True)
            return context_manager.build_grounding_snapshot(profile, recent)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to build grounding context for %s", patient_id)
            return None

    async def record_chat_turn(
        self,
        patient_id: str,
        *,
        patient_name: str,
        user_message: str,
        assistant_reply: str,
        references: list[str] | None = None,
        session_id: str | None = None,
    ) -> None:
        """Best-effort: persist one chat turn and summarize if due. Never raises."""
        try:
            profile = await memory.get_profile(patient_id)
            if profile is None:
                profile = await memory.upsert_profile(patient_id, patient_name=patient_name)

            await memory.add_event(
                patient_id, "chat_message", role="user", text=user_message,
                source_session_id=session_id,
            )
            await memory.add_event(
                patient_id, "chat_message", role="assistant", text=assistant_reply,
                payload={"references": references or []}, source_session_id=session_id,
            )

            session_ids = profile.session_ids or []
            if session_id and session_id not in session_ids:
                session_ids = [*session_ids, session_id]
            messages_since_summary = (profile.messages_since_summary or 0) + 2
            await memory.upsert_profile(
                patient_id,
                event_count=(profile.event_count or 0) + 2,
                session_ids=session_ids,
                messages_since_summary=messages_since_summary,
            )

            if context_manager.needs_summary(messages_since_summary):
                await self._summarize(patient_id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record chat turn for %s", patient_id)

    async def _summarize(self, patient_id: str) -> None:
        """Best-effort: condense recent conversation into the rolling summary."""
        try:
            profile = await memory.get_profile(patient_id)
            if profile is None:
                return
            recent = await memory.recent_chat_events(
                patient_id, limit=profile.messages_since_summary or 10,
            )
            text, provider = await get_summary_engine().summarize_conversation(
                profile.last_summary, recent,
            )
            await memory.add_event(
                patient_id, "summary", title="Conversation summary updated",
                text=text, payload={"provider": provider},
            )
            await memory.upsert_profile(
                patient_id,
                last_summary=text,
                last_summary_at=utcnow(),
                messages_since_summary=0,
            )
            logger.info("Summarized conversation for %s (%s)", patient_id, provider)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to summarize conversation for %s", patient_id)


_SERVICE: PatientContextService | None = None


def get_service() -> PatientContextService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PatientContextService()
    return _SERVICE
