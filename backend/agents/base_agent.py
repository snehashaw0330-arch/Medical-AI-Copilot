"""Base agent — the common contract + lifecycle wrapper for every agent.

Concrete agents implement one method, :meth:`process`, and declare *what* they
read/write via class attributes. The base class owns all the cross-cutting
concerns — timing, event emission, timeout, error isolation and building the
:class:`AgentRecord` — so each agent stays focused on its single responsibility
(SRP) and the pipeline behaves consistently.

An agent never terminates the workflow: a failure or timeout is captured into a
FAILED record and the engine moves on, letting downstream agents skip gracefully
if their inputs are missing. This is what makes the copilot resilient.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.agents.context_manager import AgentContext, utcnow
from backend.agents.schemas import AgentRecord, AgentStatus, EventType


@dataclass
class AgentOutcome:
    """What an agent's :meth:`process` returns (it writes its data to memory)."""

    status: AgentStatus = AgentStatus.COMPLETED
    summary: str = ""
    confidence: float | None = None          # 0..1 where meaningful
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def skipped(cls, reason: str) -> "AgentOutcome":
        return cls(status=AgentStatus.SKIPPED, summary=reason)


class BaseAgent(ABC):
    """Abstract collaborating agent. Subclasses implement :meth:`process`."""

    #: Stable name (matches config + registry + workflow stages).
    name: str = "base"
    #: Human-friendly title for the UI.
    title: str = "Base Agent"
    #: One-line responsibility statement (shown in the registry/diagram).
    description: str = ""
    #: Declared shared-memory dependencies (metadata for the diagram + docs).
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()

    @abstractmethod
    async def process(self, ctx: AgentContext) -> AgentOutcome:
        """Do the agent's work, reading/writing shared memory. Return an outcome."""

    async def health_check(self) -> tuple[bool, str]:
        """Cheap liveness probe for the agent's underlying dependency.

        Default: no dedicated dependency to probe, so the agent is assumed
        available. Agents that wrap a real external/loadable dependency (a
        model file, a dataset, the RAG index, an OCR engine) override this
        with a real, side-effect-free check. Never raises — a failing probe
        should report ``(False, reason)``, not crash health monitoring.
        """
        return True, "No dedicated health probe; assumed available."

    async def execute(self, ctx: AgentContext) -> AgentRecord:
        """Run :meth:`process` with timing, events, timeout and error isolation."""
        record = AgentRecord(name=self.name, title=self.title, status=AgentStatus.RUNNING)
        record.started_at = utcnow()
        start = ctx.elapsed_ms()
        await ctx.emit(EventType.AGENT_STARTED, self.name, f"{self.title} started")

        try:
            outcome = await asyncio.wait_for(
                self.process(ctx), timeout=ctx.config.agent_timeout
            )
            record.status = outcome.status
            record.summary = outcome.summary
            record.confidence = outcome.confidence
            record.details = outcome.details
        except asyncio.TimeoutError:
            record.status = AgentStatus.FAILED
            record.error = f"Timed out after {ctx.config.agent_timeout:.0f}s"
            ctx.logger.error("%s timed out", self.name)
        except Exception as exc:  # noqa: BLE001 — never let one agent crash the run
            record.status = AgentStatus.FAILED
            record.error = str(exc)
            ctx.logger.exception("%s failed", self.name)

        record.finished_at = utcnow()
        record.duration_ms = round(ctx.elapsed_ms() - start, 1)

        event = {
            AgentStatus.COMPLETED: EventType.AGENT_COMPLETED,
            AgentStatus.SKIPPED: EventType.AGENT_SKIPPED,
            AgentStatus.FAILED: EventType.AGENT_FAILED,
        }.get(record.status, EventType.AGENT_COMPLETED)
        await ctx.emit(
            event, self.name,
            record.error or record.summary or f"{self.title} {record.status.value}",
            payload={"confidence": record.confidence, "duration_ms": record.duration_ms},
        )
        ctx.add_record(record)
        return record
