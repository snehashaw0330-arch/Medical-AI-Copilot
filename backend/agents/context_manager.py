"""Context manager — builds and owns the per-run execution context.

The :class:`AgentContext` is the single object injected into every agent. It
bundles the collaborators an agent may use — shared memory, the event bus, a
run-scoped logger, the resolved LLM and config — so agents receive their
dependencies rather than reaching for globals (Dependency Injection).

:data:`MemoryKeys` is the shared vocabulary of blackboard keys. Centralising it
here is what lets each agent "only know its own responsibility": it reads/writes
named slots, never other agents.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.agents.config.agent_config import AgentConfig, get_agent_config
from backend.agents.event_bus import AsyncEventBus, get_event_bus
from backend.agents.logger import RunLogger
from backend.agents.memory import SharedMemory
from backend.agents.schemas import AgentRecord, EventType
from backend.llm.base_llm import BaseLLM
from backend.llm.factory import get_llm


class MemoryKeys:
    """Well-known shared-memory slots (the agents' shared vocabulary)."""

    INPUTS = "inputs"                 # raw request (image_path, symptoms, ...)
    OCR = "ocr_result"                # OCR Agent output
    MEDICINES = "medicines"           # Medicine Agent output
    DISEASE = "disease"               # Disease Agent output
    INTERACTIONS = "interactions"     # Drug-Interaction Agent output
    KNOWLEDGE = "knowledge"           # Knowledge (RAG) Agent output
    CLINICAL = "clinical"             # Clinical Decision Agent output
    EXPLANATION = "explanation"       # Explainability Agent output
    REPORT = "report"                 # Report Agent output
    AUDIT = "audit"                   # Audit Agent output


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AgentContext:
    """Everything an agent needs, injected per run."""

    run_id: str
    task_type: str
    memory: SharedMemory
    event_bus: AsyncEventBus
    logger: RunLogger
    llm: BaseLLM
    config: AgentConfig
    _t0: float = field(default_factory=time.monotonic)
    _records: list[AgentRecord] = field(default_factory=list)

    # -- shared-memory helpers --------------------------------------------
    async def get(self, key: str, default: Any = None) -> Any:
        return await self.memory.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        await self.memory.set(key, value)

    # -- observability helpers --------------------------------------------
    def elapsed_ms(self) -> float:
        return round((time.monotonic() - self._t0) * 1000, 1)

    def add_record(self, record: AgentRecord) -> None:
        self._records.append(record)

    @property
    def records(self) -> list[AgentRecord]:
        return self._records

    async def emit(
        self, type: EventType, agent: str | None = None, message: str = "",
        payload: dict | None = None,
    ) -> None:
        await self.event_bus.emit(type, self.run_id, agent, message, payload)


class ContextManager:
    """Factory for per-run :class:`AgentContext` objects (DI container).

    Collaborators are injected here so the whole app can be reconfigured (e.g. a
    fake LLM/event-bus in tests) without touching agents or the engine.
    """

    def __init__(
        self,
        *,
        event_bus: AsyncEventBus | None = None,
        llm: BaseLLM | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        self._event_bus = event_bus or get_event_bus()
        self._llm = llm or get_llm()
        self._config = config or get_agent_config()

    def create(self, run_id: str, task_type: str, inputs: dict) -> AgentContext:
        """Build a fresh context, seeding the INPUTS slot in shared memory."""
        memory = SharedMemory(seed={MemoryKeys.INPUTS: inputs})
        return AgentContext(
            run_id=run_id,
            task_type=task_type,
            memory=memory,
            event_bus=self._event_bus,
            logger=RunLogger(run_id, "workflow"),
            llm=self._llm,
            config=self._config,
        )
