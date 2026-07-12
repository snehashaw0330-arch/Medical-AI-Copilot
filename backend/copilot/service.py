"""Top-level service for the AI Medical Copilot Workspace (async).

Ties the pieces together and owns the cross-cutting concerns:

* **Session orchestration** — resolves the patient session (``context.py``), runs
  the workflow (``workflow.py``) under the session lock so concurrent uploads for
  one patient serialise, folds the result into the remembered context and records
  the conversation/activity (``memory.py``).
* **Caching** — an in-memory TTL + LRU cache keyed by a stable hash of the inputs
  (including the uploaded file's bytes), so identical re-runs skip the expensive
  OCR + model + RAG fan-out.
* **Chat / context / history** — the read + conversational surfaces the workspace
  needs.

Design contract: async everywhere, best-effort, exception-safe. A failure in any
subsystem degrades gracefully and never takes down the workspace.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict

from backend.config import settings
from backend.copilot import memory
from backend.copilot.context import Session, get_store
from backend.copilot.schemas import (
    ChatRole,
    CopilotAnalysis,
    CopilotChatResponse,
    CopilotContextResponse,
    CopilotHistoryItem,
    CopilotHistoryResponse,
    utcnow,
)
from backend.copilot.workflow import get_workflow

logger = logging.getLogger("copilot.service")


# ==========================================================================
# In-memory TTL + LRU cache (shared shape with the reasoning module)
# ==========================================================================
class _Cache:
    def __init__(self, ttl: int, size: int) -> None:
        self._ttl = ttl
        self._size = max(1, size)
        self._store: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        ts, payload = entry
        if time.time() - ts > self._ttl:
            self._store.pop(key, None)
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return payload

    def put(self, key: str, payload: dict) -> None:
        if not self.enabled:
            return
        self._store[key] = (time.time(), payload)
        self._store.move_to_end(key)
        while len(self._store) > self._size:
            self._store.popitem(last=False)

    def size(self) -> int:
        return len(self._store)


def _cache_key(*, file_hash: str | None, text, medicines, symptoms, diagnosis,
               age, gender, include_rag) -> str:
    payload = {
        "file": file_hash,
        "text": (text or "").strip().lower(),
        "medicines": sorted(m.lower().strip() for m in medicines),
        "symptoms": sorted(s.lower().strip() for s in symptoms),
        "diagnosis": (diagnosis or "").lower().strip(),
        "age": age,
        "gender": (gender or "").lower(),
        "include_rag": include_rag,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_file(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


# ==========================================================================
# Service
# ==========================================================================
class CopilotService:
    """The AI Medical Copilot orchestrator."""

    def __init__(self) -> None:
        self._cache = _Cache(settings.COPILOT_CACHE_TTL, settings.COPILOT_CACHE_SIZE)

    # -- analyze -----------------------------------------------------------
    async def analyze(
        self,
        *,
        session_id: str | None,
        image_path: str | None = None,
        text: str = "",
        medicines: list[str] | None = None,
        symptoms: list[str] | None = None,
        patient_name: str | None = None,
        age: int | None = None,
        gender: str | None = None,
        diagnosis: str | None = None,
        include_rag: bool = True,
        use_cache: bool = True,
    ) -> tuple[Session, CopilotAnalysis]:
        medicines = [m for m in (medicines or []) if m and m.strip()]
        symptoms = [s for s in (symptoms or []) if s and s.strip()]

        sess = await get_store().get_or_create(session_id)

        file_hash = _hash_file(image_path) if image_path else None
        key = _cache_key(
            file_hash=file_hash, text=text, medicines=medicines, symptoms=symptoms,
            diagnosis=diagnosis, age=age, gender=gender, include_rag=include_rag,
        )

        async with sess.lock:
            # Caller-supplied patient identity is authoritative — remember it for
            # the session (OCR-derived fields still backfill later via apply_analysis).
            if patient_name:
                sess.context.patient_name = patient_name
            if age is not None:
                sess.context.age = age
            if gender:
                sess.context.gender = gender.lower()
            # Track the reported symptoms on the context immediately.
            if symptoms:
                sess.context.symptoms = _merge(sess.context.symptoms, symptoms)

            analysis: CopilotAnalysis | None = None
            if use_cache:
                cached = self._cache.get(key)
                if cached is not None:
                    analysis = CopilotAnalysis(**cached)
                    analysis.analysis_id = uuid.uuid4().hex
                    analysis.created_at = utcnow()
                    analysis.cached = True
                    analysis.session_id = sess.id
                    logger.info("Copilot cache hit (%s…) session=%s", key[:10], sess.id[:8])

            if analysis is None:
                analysis = await get_workflow().run(
                    session_id=sess.id, image_path=image_path, text=text,
                    medicines=medicines, symptoms=symptoms, patient_name=patient_name,
                    age=age, gender=gender, diagnosis=diagnosis, include_rag=include_rag,
                )
                self._cache.put(key, analysis.model_dump(mode="json"))

            # Fold into the remembered patient context + conversation.
            get_store().apply_analysis(sess, analysis)
            memory.add_message(
                sess, ChatRole.ASSISTANT,
                analysis.summary or "Analysis complete.",
                references=[r.label for r in analysis.references],
            )
            return sess, analysis

    # -- chat --------------------------------------------------------------
    async def chat(self, session_id: str, message: str) -> CopilotChatResponse:
        sess = await get_store().get(session_id)
        if sess is None:
            raise KeyError(session_id)

        async with sess.lock:
            memory.add_message(sess, ChatRole.USER, message)
            snapshot = memory.patient_snapshot(sess.context)
            convo = memory.transcript(sess, limit=10)
            patient_name = sess.context.patient_name          # NEW

        # NEW — Step 1: retrieve durable, cross-session patient memory. This is
        # a separate module/DB (backend.patient_context) and must never break
        # chat if the patient can't be identified yet or the store is down.
        patient_id: str | None = None                                             # NEW
        pc_service = None                                                         # NEW
        if settings.COPILOT_USE_PATIENT_CONTEXT and patient_name:                 # NEW
            try:                                                                  # NEW
                from backend.patient_context.context_manager import slugify as pc_slugify  # NEW
                from backend.patient_context.service import get_service as get_pc_service  # NEW

                patient_id = pc_slugify(patient_name)                             # NEW
                pc_service = get_pc_service()                                     # NEW
                remembered = await pc_service.get_grounding_context(patient_id)   # NEW
                if remembered:                                                    # NEW
                    snapshot = f"{snapshot}\n\nRemembered patient history:\n{remembered}"  # NEW
            except Exception as exc:  # noqa: BLE001                              # NEW
                logger.warning("patient_context memory unavailable: %s", exc)     # NEW
                patient_id = None                                                 # NEW

        # NEW — Step 2: retrieve relevant medical knowledge via RAG (chat
        # currently skips RAG retrieval entirely — this closes that gap).
        # Best-effort: degrades to no extra evidence if no index is built yet.
        if settings.COPILOT_USE_RAG:                                              # NEW
            try:                                                                  # NEW
                from backend.rag.retriever import get_retriever                   # NEW

                retriever = get_retriever()                                       # NEW
                if retriever.available():                                        # NEW
                    chunks = await asyncio.to_thread(retriever.retrieve, message, top_k=4)  # NEW
                    if chunks:                                                    # NEW
                        evidence = "\n".join(f"- ({c.source}) {c.text[:300]}" for c in chunks)  # NEW
                        # NEW — Step 3: combine memory + evidence into the snapshot.
                        snapshot = f"{snapshot}\n\nRelevant medical knowledge:\n{evidence}"  # NEW
            except Exception as exc:  # noqa: BLE001                              # NEW
                logger.warning("RAG retrieval unavailable for chat: %s", exc)     # NEW

        from backend.copilot.summary import get_engine as get_summary_engine

        # Step 4 — generate the personalized response (unchanged call).
        reply, provider = await get_summary_engine().chat(
            system_context=snapshot, transcript=convo, question=message,
        )

        async with sess.lock:
            # Reference the most recent analysis's evidence, if any.
            refs: list[str] = []
            if sess.analyses:
                refs = [e.title for e in sess.analyses[0].evidence][:5]
            memory.add_message(sess, ChatRole.ASSISTANT, reply, references=refs)

        # NEW — Step 5: store the updated conversation summary in durable
        # memory. Best-effort: never raises, so a patient_context/LLM failure
        # here can never turn a successful chat reply into a 500.
        if patient_id and pc_service is not None:                                 # NEW
            try:                                                                  # NEW
                await pc_service.record_chat_turn(                                # NEW
                    patient_id, patient_name=patient_name, user_message=message,  # NEW
                    assistant_reply=reply, references=refs, session_id=sess.id,   # NEW
                )                                                                 # NEW
            except Exception as exc:  # noqa: BLE001                              # NEW
                logger.warning("Failed to persist patient_context chat turn: %s", exc)  # NEW

        return CopilotChatResponse(
            session_id=sess.id, reply=reply, references=refs,
            reasoning="Grounded in the current patient session context.",
            provider=provider,
        )

    # -- reads -------------------------------------------------------------
    async def get_context(self, session_id: str) -> CopilotContextResponse:
        sess = await get_store().get(session_id)
        if sess is None:
            raise KeyError(session_id)
        from backend.llm import available_providers

        try:
            llm_info = available_providers()
        except Exception:  # noqa: BLE001
            llm_info = {}
        return CopilotContextResponse(
            context=sess.context,
            messages=sess.messages[-40:],
            last_analysis=sess.analyses[0] if sess.analyses else None,
            llm=llm_info if isinstance(llm_info, dict) else {"providers": llm_info},
        )

    async def get_history(self, session_id: str) -> CopilotHistoryResponse:
        sess = await get_store().get(session_id)
        if sess is None:
            raise KeyError(session_id)
        items = [
            CopilotHistoryItem(
                analysis_id=a.analysis_id, created_at=a.created_at,
                title=(a.disease_prediction[0].disease if a.disease_prediction
                       else f"{len(a.medicines)} medicine(s)"),
                leading_disease=a.disease_prediction[0].disease if a.disease_prediction else None,
                medicine_count=len(a.medicines), risk_level=a.risk_level,
                confidence=a.confidence, report_id=a.report_id,
            )
            for a in sess.analyses
        ]
        return CopilotHistoryResponse(session_id=sess.id, items=items, total=len(items))

    def cache_stats(self) -> dict:
        return {
            "hits": self._cache.hits, "misses": self._cache.misses,
            "size": self._cache.size(), "active_sessions": get_store().active_count(),
        }


def _merge(existing: list[str], incoming: list[str]) -> list[str]:
    seen = {e.lower() for e in existing}
    out = list(existing)
    for i in incoming:
        if i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out


_SERVICE: CopilotService | None = None


def get_service() -> CopilotService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = CopilotService()
    return _SERVICE
