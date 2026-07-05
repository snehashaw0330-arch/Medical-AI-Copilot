"""Task router — maps an incoming request to a workflow plan.

Given the raw inputs, it classifies the task (a full *prescription* scan, a
*symptoms* check, a *medicines* lookup, or a mix) and returns the plan of stages
to execute. Today all task types run the same full pipeline — agents whose inputs
are absent skip themselves cheaply — but centralising routing here means new task
types or alternate pipelines can be introduced without touching the engine or the
manager (SRP + Open-Closed).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.agents.config.workflow_config import WorkflowConfig, get_workflow_config


@dataclass
class RoutePlan:
    """The resolved plan for a run: a task label + the stages to execute."""

    task_type: str
    stages: list[list[str]]


class TaskRouter:
    """Classifies inputs and selects the workflow stages to run."""

    def __init__(self, workflow: WorkflowConfig | None = None) -> None:
        self._workflow = workflow or get_workflow_config()

    @staticmethod
    def classify(inputs: dict) -> str:
        """Label the task from what the caller supplied (for observability)."""
        if inputs.get("image_path"):
            return "prescription"
        if inputs.get("symptoms"):
            return "symptoms"
        if inputs.get("medicines"):
            return "medicines"
        if inputs.get("text"):
            return "free_text"
        return "empty"

    def route(self, inputs: dict) -> RoutePlan:
        """Return the plan for these inputs (full pipeline; agents self-skip)."""
        task_type = self.classify(inputs)
        # Copy the declarative stages so callers can't mutate the shared config.
        stages = [list(stage) for stage in self._workflow.stages]
        return RoutePlan(task_type=task_type, stages=stages)
