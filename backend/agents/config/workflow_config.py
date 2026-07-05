"""Workflow definition: the ordered stages of the medical copilot pipeline.

A *stage* is a list of agent names that run **concurrently** (they have no data
dependency on each other); stages run sequentially. This declarative shape is
what lets the engine run independent agents in parallel while honouring the
overall order:

    OCR → Medicine → (Disease ‖ Drug-Interaction) → Knowledge →
    Clinical → Explainability → Report → Audit

Disease and Drug-Interaction are independent (one reads symptoms, the other reads
the medicine list), so they form a single concurrent stage — demonstrating the
parallelism the requirements ask for. Editing this list reshapes the pipeline
without touching any agent or the engine (Open-Closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.agents.config import agent_config as ac


@dataclass
class WorkflowConfig:
    """Declarative pipeline: a sequence of concurrent stages."""

    stages: list[list[str]] = field(default_factory=lambda: [
        [ac.OCR],
        [ac.MEDICINE],
        [ac.DISEASE, ac.DRUG_INTERACTION],   # concurrent
        [ac.KNOWLEDGE],
        [ac.CLINICAL],
        [ac.EXPLAINABILITY],
        [ac.REPORT],
        [ac.AUDIT],
    ])

    def ordered_agents(self) -> list[str]:
        """Flat, ordered agent list (for the UI's static workflow diagram)."""
        return [name for stage in self.stages for name in stage]


def get_workflow_config() -> WorkflowConfig:
    return WorkflowConfig()
