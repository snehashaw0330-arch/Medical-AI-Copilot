"""Pydantic contracts for the agent layer (API + run-state + observability).

These are the stable boundary between the workflow engine, the run store and the
React "AI Agent Monitor" page. Keeping them in one place means the frontend
timeline, the pipeline diagram and the audit log all speak the same shapes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentStatus(str, Enum):
    """Lifecycle state of a single agent within a run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"      # ran but had no work to do (missing inputs)
    FAILED = "failed"


class RunStatus(str, Enum):
    """Lifecycle state of a whole workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(str, Enum):
    """Event-bus message types (drive the live monitor + audit trail)."""

    WORKFLOW_STARTED = "workflow_started"
    STAGE_STARTED = "stage_started"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_SKIPPED = "agent_skipped"
    AGENT_FAILED = "agent_failed"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    LOG = "log"


class AgentRecord(BaseModel):
    """Per-agent execution record (observability + audit)."""

    name: str
    title: str = ""
    status: AgentStatus = AgentStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    confidence: float | None = None          # 0..1 where meaningful
    summary: str = ""
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    """One entry in the run timeline (what the UI animates)."""

    type: EventType
    agent: str | None = None
    message: str = ""
    timestamp: datetime
    elapsed_ms: float = 0.0


class AgentMeta(BaseModel):
    """Static descriptor of a registered agent (registry endpoint + diagram)."""

    name: str
    title: str
    description: str = ""
    reads: list[str] = []
    writes: list[str] = []
    enabled: bool = True


class RunState(BaseModel):
    """The full, live state of a workflow run (polled by the monitor page)."""

    run_id: str
    task_type: str = "prescription"
    status: RunStatus = RunStatus.PENDING
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0

    current_agent: str | None = None
    completed_agents: int = 0
    total_agents: int = 0
    progress: float = 0.0                    # 0..1

    overall_confidence: float | None = None
    agents: list[AgentRecord] = []
    timeline: list[TimelineEvent] = []
    logs: list[str] = []
    result: dict[str, Any] = Field(default_factory=dict)   # sanitized summary
    error: str | None = None


class RunCreated(BaseModel):
    """Response for ``POST /agents/run`` — the run id to poll."""

    run_id: str
    status: RunStatus
    task_type: str


class RegistryInfo(BaseModel):
    """Response for ``GET /agents/registry`` — agents + workflow + providers."""

    agents: list[AgentMeta] = []
    workflow: list[list[str]] = []           # stages (concurrent groups)
    ordered: list[str] = []                  # flat ordered agent list
    llm_provider: str = "offline"
    llm_providers: dict[str, Any] = {}


class RunListItem(BaseModel):
    """Lightweight row for the recent-runs list."""

    run_id: str
    status: RunStatus
    task_type: str
    created_at: datetime
    duration_ms: float = 0.0
    overall_confidence: float | None = None


class AgentHealth(BaseModel):
    """Live liveness/availability probe result for one agent."""

    name: str
    title: str = ""
    healthy: bool = True
    enabled: bool = True
    detail: str = ""
    checked_at: datetime = Field(default_factory=_utcnow)


class HealthReport(BaseModel):
    """Aggregate health snapshot across every registered agent (``GET /agents/health``)."""

    status: str = "ok"           # "ok" | "degraded" | "down"
    total_agents: int = 0
    healthy_agents: int = 0
    enabled_agents: int = 0
    llm_provider: str = "offline"
    agents: list[AgentHealth] = []
    checked_at: datetime = Field(default_factory=_utcnow)
