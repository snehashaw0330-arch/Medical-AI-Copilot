"""Audit Agent — record every step, agent, timing, confidence and error.

Runs last. It reads the execution trail the engine accumulated on the context
(one :class:`AgentRecord` per agent that ran) and compiles a structured decision
log: per-agent status/latency/confidence/errors plus run-level totals. This is
the durable, auditable account of *how* the copilot reached its conclusions.
"""

from __future__ import annotations

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys
from backend.agents.schemas import AgentStatus


class AuditAgent(BaseAgent):
    name = ac.AUDIT
    title = "Audit Agent"
    description = "Record every step, agent, execution time, confidence and error into a decision log."
    reads = ()
    writes = (MemoryKeys.AUDIT,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        # The engine appends each finished agent's record to the context trail.
        records = ctx.records  # all agents before Audit (Audit is appended after).

        steps = [{
            "name": r.name, "title": r.title, "status": r.status.value,
            "duration_ms": r.duration_ms, "confidence": r.confidence,
            "summary": r.summary, "error": r.error,
        } for r in records]

        confidences = [r.confidence for r in records if r.confidence is not None]
        total_time = round(sum(r.duration_ms for r in records), 1)
        audit = {
            "steps": steps,
            "totals": {
                "agents_run": len(records),
                "completed": sum(1 for r in records if r.status == AgentStatus.COMPLETED),
                "skipped": sum(1 for r in records if r.status == AgentStatus.SKIPPED),
                "failed": sum(1 for r in records if r.status == AgentStatus.FAILED),
                "total_time_ms": total_time,
                "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
            },
            "order": [r.name for r in records] + [self.name],
            "run_id": ctx.run_id,
        }
        await ctx.set(MemoryKeys.AUDIT, audit)
        ctx.logger.info(
            "Audit: %d agent(s), %d failed, total %.0fms",
            audit["totals"]["agents_run"], audit["totals"]["failed"], total_time,
        )
        return AgentOutcome(
            summary=f"Audited {len(records)} step(s); {audit['totals']['failed']} failed.",
            confidence=None,
            details=audit["totals"],
        )
