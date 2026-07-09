"""Session-scoped patient context store for the Copilot (in-memory, async-safe).

The Copilot "remembers the current patient during the session": every upload
updates one evolving :class:`PatientContext`. This module owns that state.

* A :class:`Session` bundles the patient context, the conversation, the recorded
  analyses and a per-session :class:`asyncio.Lock` (so concurrent uploads for the
  same session serialise their context mutations).
* :class:`ContextStore` is a process-wide **TTL + LRU** dict of sessions, so idle
  sessions are reclaimed and total memory stays bounded.

Everything is in-memory by design — a patient session is ephemeral working state,
not a system of record. Durable artefacts (medical reports) are still persisted by
the existing report store; the Copilot only keeps pointers to them.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from backend.config import settings
from backend.copilot.schemas import (
    CopilotAnalysis,
    ChatMessage,
    PatientContext,
    ReportRef,
    utcnow,
)

logger = logging.getLogger("copilot.context")


def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
    """Case-insensitive union that preserves order and original casing."""
    seen = {e.lower() for e in existing}
    out = list(existing)
    for item in incoming:
        norm = (item or "").strip()
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            out.append(norm)
    return out


@dataclass
class Session:
    """All working state for one patient session."""

    id: str
    context: PatientContext
    messages: list[ChatMessage] = field(default_factory=list)
    analyses: list[CopilotAnalysis] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_seen = time.time()


class ContextStore:
    """Process-wide TTL + LRU store of patient sessions."""

    def __init__(self, *, ttl: int, max_sessions: int) -> None:
        self._ttl = ttl
        self._max = max(1, max_sessions)
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._guard = asyncio.Lock()

    # -- lifecycle ---------------------------------------------------------
    async def get_or_create(self, session_id: str | None) -> Session:
        """Return the session for *session_id*, creating one if needed."""
        async with self._guard:
            self._evict_expired_locked()
            if session_id and session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.touch()
                self._sessions.move_to_end(session_id)
                return sess

            new_id = session_id or uuid.uuid4().hex
            sess = Session(id=new_id, context=PatientContext(session_id=new_id))
            self._sessions[new_id] = sess
            self._sessions.move_to_end(new_id)
            while len(self._sessions) > self._max:
                old_id, _ = self._sessions.popitem(last=False)
                logger.info("Evicted oldest Copilot session %s (capacity)", old_id[:8])
            logger.info("Created Copilot session %s", new_id[:8])
            return sess

    async def get(self, session_id: str) -> Session | None:
        async with self._guard:
            self._evict_expired_locked()
            sess = self._sessions.get(session_id)
            if sess:
                sess.touch()
                self._sessions.move_to_end(session_id)
            return sess

    def _evict_expired_locked(self) -> None:
        if self._ttl <= 0:
            return
        cutoff = time.time() - self._ttl
        expired = [sid for sid, s in self._sessions.items() if s.last_seen < cutoff]
        for sid in expired:
            self._sessions.pop(sid, None)
        if expired:
            logger.info("Evicted %d expired Copilot session(s)", len(expired))

    def active_count(self) -> int:
        return len(self._sessions)

    # -- context mutation (call under the session lock) --------------------
    def apply_analysis(self, sess: Session, analysis: CopilotAnalysis) -> None:
        """Fold one analysis into the patient context (the 'memory update')."""
        ctx = sess.context

        # Patient identity: fill from OCR/derived fields without clobbering a
        # value the user already established, unless the new one is non-empty.
        ocr_fields = (analysis.ocr.fields if analysis.ocr else {}) or {}
        name = ctx.patient_name or ocr_fields.get("patient")
        if name:
            ctx.patient_name = name
        if ctx.age is None:
            age = _coerce_age(ocr_fields.get("age"))
            if age is not None:
                ctx.age = age
        if not ctx.gender and ocr_fields.get("gender"):
            ctx.gender = str(ocr_fields["gender"]).lower()

        # Accumulate the working picture.
        ctx.current_medicines = _merge_unique(ctx.current_medicines, analysis.medicines)
        diagnosis = ocr_fields.get("diagnosis")
        if diagnosis:
            ctx.known_conditions = _merge_unique(ctx.known_conditions, [diagnosis])
        if analysis.disease_prediction:
            ctx.known_conditions = _merge_unique(
                ctx.known_conditions, [analysis.disease_prediction[0].disease]
            )

        # Previous-reports pointer for the left panel.
        leading = analysis.disease_prediction[0].disease if analysis.disease_prediction else None
        ctx.previous_reports.insert(0, ReportRef(
            analysis_id=analysis.analysis_id,
            report_id=analysis.report_id,
            created_at=analysis.created_at,
            title=leading or (f"{len(analysis.medicines)} medicine(s)" if analysis.medicines else "Analysis"),
            leading_disease=leading,
            medicine_count=len(analysis.medicines),
            risk_level=analysis.risk_level,
        ))
        ctx.previous_reports = ctx.previous_reports[: settings.COPILOT_MAX_ANALYSES]

        # Timeline: prepend the analysis's activity events (newest first).
        ctx.timeline = (list(analysis.activity) + ctx.timeline)[: settings.COPILOT_MAX_TIMELINE]

        ctx.analysis_count += 1
        ctx.updated_at = utcnow()

        # Keep the bounded rolling window of full analyses.
        sess.analyses.insert(0, analysis)
        del sess.analyses[settings.COPILOT_MAX_ANALYSES:]


def _coerce_age(value) -> int | None:
    """Parse an age from an OCR string like '68', '68 yrs', '68Y'."""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    try:
        age = int(digits[:3])
        return age if 0 <= age <= 120 else None
    except ValueError:
        return None


_STORE: ContextStore | None = None


def get_store() -> ContextStore:
    global _STORE
    if _STORE is None:
        _STORE = ContextStore(
            ttl=settings.COPILOT_SESSION_TTL,
            max_sessions=settings.COPILOT_MAX_SESSIONS,
        )
    return _STORE
