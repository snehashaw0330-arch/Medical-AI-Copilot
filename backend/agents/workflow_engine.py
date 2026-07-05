"""Workflow engine — executes the staged, event-driven agent pipeline.

Responsibilities (only these — SRP):

* run the plan's stages **in order**, and the agents **within a stage
  concurrently** (`asyncio.gather`) since a stage groups independent agents;
* emit workflow/stage lifecycle events on the bus (the live monitor listens);
* skip disabled agents (registry/config) and isolate agent failures;
* compute the overall confidence from the agents that reported one.

It knows nothing about *which* agents exist or *what* they do — it is handed a
registry and a plan. That decoupling is what makes the pipeline reconfigurable
(via `workflow_config`) without engine changes.
"""

from __future__ import annotations

from backend.agents.agent_registry import AgentRegistry
from backend.agents.context_manager import AgentContext
from backend.agents.logger import get_logger
from backend.agents.schemas import AgentRecord, AgentStatus, EventType
from backend.agents.task_router import RoutePlan

logger = get_logger("engine")


class WorkflowEngine:
    """Runs a :class:`RoutePlan` against a registry within an :class:`AgentContext`."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def run(self, ctx: AgentContext, plan: RoutePlan) -> list[AgentRecord]:
        """Execute every stage; return the ordered list of agent records."""
        import asyncio

        enabled_stages = [
            [name for name in stage if self._registry.is_enabled(name)]
            for stage in plan.stages
        ]
        total = sum(len(s) for s in enabled_stages)
        await ctx.emit(
            EventType.WORKFLOW_STARTED, message=f"Pipeline started ({total} agents)",
            payload={"task_type": plan.task_type, "total_agents": total},
        )

        records: list[AgentRecord] = []
        try:
            for stage in enabled_stages:
                if not stage:
                    continue
                await ctx.emit(
                    EventType.STAGE_STARTED,
                    message="Stage: " + ", ".join(stage),
                    payload={"agents": stage},
                )
                agents = [self._registry.get(name) for name in stage]
                # Independent agents in a stage run concurrently.
                stage_records = await asyncio.gather(
                    *(agent.execute(ctx) for agent in agents)
                )
                records.extend(stage_records)

            confidence = self._overall_confidence(records)
            await ctx.emit(
                EventType.WORKFLOW_COMPLETED,
                message="Pipeline completed",
                payload={"overall_confidence": confidence,
                         "failed": [r.name for r in records if r.status == AgentStatus.FAILED]},
            )
            return records
        except Exception as exc:  # noqa: BLE001 — should be rare; agents self-isolate
            logger.exception("Workflow engine crashed")
            await ctx.emit(EventType.WORKFLOW_FAILED, message=str(exc))
            raise

    @staticmethod
    def _overall_confidence(records: list[AgentRecord]) -> float | None:
        """Mean of the agents that reported a confidence (0..1)."""
        vals = [r.confidence for r in records if r.confidence is not None]
        return round(sum(vals) / len(vals), 3) if vals else None
