"""Agent Manager — the façade that wires the whole agent subsystem together.

This is the composition root: it constructs (or accepts, for tests) every
collaborator — context manager, registry, workflow engine, task router, run store
— and exposes two entry points:

* :meth:`start_run`   — seed a run, launch the pipeline in the background and
  return a ``run_id`` immediately (for live monitoring).
* :meth:`run_and_wait` — run the pipeline to completion and return the final
  state (used by the OCR auto-hook, tests and synchronous callers).

All dependencies are injected (Dependency Injection): swap in a fake LLM, event
bus or registry and the manager is fully testable without any network/model.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path

from backend.agents.agent_registry import AGENT_SPECS, AgentRegistry
from backend.agents.context_manager import ContextManager, MemoryKeys
from backend.agents.logger import get_logger
from backend.agents.run_store import RunStore, get_run_store
from backend.agents.schemas import RegistryInfo, RunState, RunStatus
from backend.agents.task_router import RoutePlan, TaskRouter
from backend.agents.workflow_engine import WorkflowEngine
from backend.llm.factory import available_providers, get_llm

logger = get_logger("manager")


class AgentManager:
    """Orchestrates a full multi-agent run and exposes its live/finished state."""

    def __init__(
        self,
        *,
        context_manager: ContextManager | None = None,
        registry: AgentRegistry | None = None,
        engine: WorkflowEngine | None = None,
        router: TaskRouter | None = None,
        run_store: RunStore | None = None,
    ) -> None:
        self._registry = registry or AgentRegistry()
        self._context = context_manager or ContextManager()
        self._engine = engine or WorkflowEngine(self._registry)
        self._router = router or TaskRouter()
        self._store = run_store or get_run_store()

    # -- public API --------------------------------------------------------
    def start_run(self, inputs: dict) -> RunState:
        """Seed a run, launch it in the background, return the seeded state."""
        run_id, plan = self._prepare(inputs)
        seeded = self._store.get(run_id)
        # Fire-and-forget; the run store tracks progress via the event bus.
        asyncio.create_task(self._execute(run_id, plan, inputs))
        return seeded  # PENDING state with the full agent list

    async def run_and_wait(self, inputs: dict) -> RunState:
        """Run the pipeline to completion and return the final state."""
        run_id, plan = self._prepare(inputs)
        await self._execute(run_id, plan, inputs)
        return self._store.get(run_id)

    def get_run(self, run_id: str) -> RunState | None:
        return self._store.get(run_id)

    def list_runs(self, limit: int = 20) -> list[RunState]:
        return self._store.list(limit)

    def registry_info(self) -> RegistryInfo:
        """Agents + workflow + LLM providers (for the monitor's static diagram)."""
        from backend.agents.config.workflow_config import get_workflow_config

        wf = get_workflow_config()
        return RegistryInfo(
            agents=self._registry.meta(),
            workflow=[list(s) for s in wf.stages],
            ordered=wf.ordered_agents(),
            llm_provider=get_llm().name,
            llm_providers=available_providers(),
        )

    # -- internals ---------------------------------------------------------
    def _prepare(self, inputs: dict) -> tuple[str, RoutePlan]:
        run_id = uuid.uuid4().hex
        plan = self._router.route(inputs)
        # Seed the run store with the enabled agents in pipeline order.
        seed = [
            (name, AGENT_SPECS[name].title)
            for name in plan_ordered(plan)
            if self._registry.is_enabled(name)
        ]
        self._store.create(run_id, plan.task_type, seed)
        return run_id, plan

    async def _execute(self, run_id: str, plan: RoutePlan, inputs: dict) -> None:
        """Run the pipeline and finalise the run state (never raises)."""
        ctx = self._context.create(run_id, plan.task_type, inputs)
        status = RunStatus.COMPLETED
        error: str | None = None
        records = []
        try:
            records = await self._engine.run(ctx, plan)
            if any(r.status.value == "failed" for r in records):
                # Partial success — the run completed but some agents failed.
                status = RunStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001 — belt-and-braces; engine self-isolates
            logger.exception("Run %s failed", run_id)
            status = RunStatus.FAILED
            error = str(exc)
        finally:
            result = await self._build_result(ctx)
            confidence = self._engine._overall_confidence(records) if records else None
            self._store.finalize(
                run_id, records, status=status, result=result,
                overall_confidence=confidence, error=error,
            )
            # Clean up an uploaded image we were given ownership of.
            if inputs.get("owns_image") and inputs.get("image_path"):
                with contextlib.suppress(Exception):
                    Path(inputs["image_path"]).unlink(missing_ok=True)

    async def _build_result(self, ctx) -> dict:
        """Compact, sanitised summary of the shared memory for the API/UI."""
        snap = await ctx.memory.snapshot()

        def _get(key: str) -> dict:
            val = snap.get(key)
            return val if isinstance(val, dict) else {}

        ocr = _get(MemoryKeys.OCR)
        medicines = _get(MemoryKeys.MEDICINES)
        disease = _get(MemoryKeys.DISEASE)
        interactions = _get(MemoryKeys.INTERACTIONS)
        knowledge = _get(MemoryKeys.KNOWLEDGE)
        clinical = _get(MemoryKeys.CLINICAL)
        report = _get(MemoryKeys.REPORT)
        return {
            "ocr": {
                "provider": ocr.get("provider"),
                "medicine_count": len(ocr.get("medicines", []) or []),
                "overall_confidence": ocr.get("overall_confidence"),
            } if ocr else None,
            "medicines": medicines.get("names", []) if medicines else [],
            "disease": (disease.get("predictions", [])[:3] if disease else []),
            "interactions": {
                "overall_risk": interactions.get("overall_risk"),
                "count": interactions.get("interaction_count"),
            } if interactions else None,
            "knowledge_sources": knowledge.get("sources", []) if knowledge else [],
            "clinical": {
                "risk_level": clinical.get("risk_level"),
                "summary": clinical.get("summary"),
            } if clinical else None,
            "report_id": report.get("report_id") if report else None,
            "explanation": bool(snap.get(MemoryKeys.EXPLANATION)),
        }


def plan_ordered(plan: RoutePlan) -> list[str]:
    """Flatten a plan's stages into an ordered agent-name list."""
    return [name for stage in plan.stages for name in stage]


# Process-wide singleton manager.
_MANAGER: AgentManager | None = None


def get_manager() -> AgentManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = AgentManager()
    return _MANAGER
