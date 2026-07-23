"""Run store — the live, in-memory state of every workflow run (observability).

Subscribes to the event bus and turns the stream of workflow/agent events into a
:class:`RunState` the frontend polls: per-agent status, a timeline, logs,
progress, the current agent and the overall confidence. The manager seeds a run
(so the UI shows the full pipeline as PENDING immediately) and finalises it with
the authoritative agent records when the pipeline ends.

In-memory by design (live monitoring); the durable record of a run lives in the
Audit Agent's output + the existing per-feature history stores. A bounded LRU cap
prevents unbounded growth.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime, timezone

from backend.agents.event_bus import Event, get_event_bus
from backend.agents.schemas import (
    AgentRecord,
    AgentStatus,
    EventType,
    RunState,
    RunStatus,
    TimelineEvent,
)

_MAX_RUNS = 100


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStore:
    """Thread-safe store of live run states, updated from the event bus."""

    def __init__(self) -> None:
        self._runs: "OrderedDict[str, RunState]" = OrderedDict()
        self._lock = threading.Lock()

    # -- lifecycle (called by the manager) --------------------------------
    def create(self, run_id: str, task_type: str, agents: list[tuple[str, str]]) -> RunState:
        """Seed a run with all its agents as PENDING so the UI shows the pipeline."""
        state = RunState(
            run_id=run_id,
            task_type=task_type,
            status=RunStatus.PENDING,
            created_at=_utcnow(),
            total_agents=len(agents),
            agents=[AgentRecord(name=n, title=t, status=AgentStatus.PENDING) for n, t in agents],
        )
        with self._lock:
            self._runs[run_id] = state
            self._runs.move_to_end(run_id)
            while len(self._runs) > _MAX_RUNS:
                self._runs.popitem(last=False)
        return state

    def finalize(
        self, run_id: str, records: list[AgentRecord], *,
        status: RunStatus, result: dict, overall_confidence: float | None,
        error: str | None = None,
    ) -> None:
        """Write the authoritative final records + result summary."""
        with self._lock:
            state = self._runs.get(run_id)
            if not state:
                return
            by_name = {r.name: r for r in records}
            # Replace seeded records with the real ones (preserving order).
            state.agents = [by_name.get(a.name, a) for a in state.agents]
            state.status = status
            state.finished_at = _utcnow()
            state.duration_ms = round(
                (state.finished_at - (state.started_at or state.created_at)).total_seconds() * 1000, 1
            )
            state.result = result
            state.overall_confidence = overall_confidence
            state.error = error
            state.current_agent = None
            state.completed_agents = sum(
                1 for a in state.agents if a.status in (AgentStatus.COMPLETED, AgentStatus.SKIPPED)
            )
            state.progress = 1.0

    # -- event subscription (live updates) --------------------------------
    def apply(self, event: Event) -> None:
        """Event-bus handler: fold one event into its run's live state."""
        with self._lock:
            state = self._runs.get(event.run_id)
            if state is None:
                return
            elapsed = round(
                (event.timestamp - state.created_at).total_seconds() * 1000, 1
            )
            state.timeline.append(TimelineEvent(
                type=event.type, agent=event.agent, message=event.message,
                timestamp=event.timestamp, elapsed_ms=elapsed,
            ))
            state.logs.append(
                f"{event.timestamp.strftime('%H:%M:%S')} "
                f"[{event.type.value}]{(' ' + event.agent) if event.agent else ''}: {event.message}"
            )
            if len(state.logs) > 500:
                state.logs = state.logs[-500:]

            if event.type == EventType.WORKFLOW_STARTED:
                state.status = RunStatus.RUNNING
                state.started_at = event.timestamp
            elif event.type == EventType.AGENT_STARTED:
                state.current_agent = event.agent
                self._set_agent(state, event.agent, AgentStatus.RUNNING, started_at=event.timestamp)
            elif event.type in (
                EventType.AGENT_COMPLETED, EventType.AGENT_SKIPPED, EventType.AGENT_FAILED,
            ):
                status = {
                    EventType.AGENT_COMPLETED: AgentStatus.COMPLETED,
                    EventType.AGENT_SKIPPED: AgentStatus.SKIPPED,
                    EventType.AGENT_FAILED: AgentStatus.FAILED,
                }[event.type]
                self._set_agent(
                    state, event.agent, status,
                    confidence=event.payload.get("confidence"),
                    duration_ms=event.payload.get("duration_ms"),
                    finished_at=event.timestamp,
                )
                state.completed_agents = sum(
                    1 for a in state.agents
                    if a.status in (AgentStatus.COMPLETED, AgentStatus.SKIPPED, AgentStatus.FAILED)
                )
                if state.total_agents:
                    state.progress = round(state.completed_agents / state.total_agents, 3)
            elif event.type == EventType.WORKFLOW_COMPLETED:
                state.overall_confidence = event.payload.get("overall_confidence")
                state.current_agent = None
            elif event.type == EventType.WORKFLOW_FAILED:
                state.status = RunStatus.FAILED
                state.error = event.message

    @staticmethod
    def _set_agent(
        state: RunState, name: str | None, status: AgentStatus,
        *, confidence: float | None = None, duration_ms: float | None = None,
        started_at: datetime | None = None, finished_at: datetime | None = None,
    ) -> None:
        for rec in state.agents:
            if rec.name == name:
                rec.status = status
                if confidence is not None:
                    rec.confidence = confidence
                if duration_ms is not None:
                    rec.duration_ms = duration_ms
                if started_at is not None:
                    rec.started_at = started_at
                if finished_at is not None:
                    rec.finished_at = finished_at
                return

    # -- reads ------------------------------------------------------------
    def get(self, run_id: str) -> RunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self, limit: int = 20) -> list[RunState]:
        with self._lock:
            return list(reversed(list(self._runs.values())))[:limit]


# Process-wide singleton, wired to the event bus on first use.
_STORE: RunStore | None = None


def get_run_store() -> RunStore:
    global _STORE
    if _STORE is None:
        _STORE = RunStore()
        get_event_bus().subscribe(_STORE.apply)
    return _STORE
