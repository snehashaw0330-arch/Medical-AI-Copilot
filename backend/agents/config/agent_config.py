"""Per-agent configuration: enable/disable + tuning knobs.

Agents can be turned off individually via ``AGENTS_DISABLED`` (comma-separated
agent names) without code changes — the registry consults this at build time and
the workflow engine simply skips disabled agents. This is how the requirement
"allow enabling/disabling agents" is satisfied.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Canonical agent names (must match the implementations' ``name`` attributes).
OCR = "ocr"
MEDICINE = "medicine"
DISEASE = "disease"
DRUG_INTERACTION = "drug_interaction"
KNOWLEDGE = "knowledge"
CLINICAL = "clinical"
EXPLAINABILITY = "explainability"
EVIDENCE_VERIFICATION = "evidence_verification"
REPORT = "report"
AUDIT = "audit"

ALL_AGENTS = (
    OCR, MEDICINE, DISEASE, DRUG_INTERACTION, KNOWLEDGE,
    CLINICAL, EXPLAINABILITY, EVIDENCE_VERIFICATION, REPORT, AUDIT,
)


@dataclass
class AgentConfig:
    """Resolved agent settings."""

    disabled: frozenset[str] = field(default_factory=frozenset)
    # Hard per-agent timeout (seconds) — a stuck agent never blocks the pipeline.
    # Generous by default to accommodate first-run ML/RAG cold-start loading
    # (dataset, disease model, embeddings); warm calls are far faster.
    agent_timeout: float = 240.0
    # Max medicines processed per run (bounds cost on huge prescriptions).
    max_medicines: int = 25

    def is_enabled(self, name: str) -> bool:
        return name not in self.disabled


def get_agent_config() -> AgentConfig:
    raw = os.getenv("AGENTS_DISABLED", "")
    disabled = frozenset(
        a.strip().lower() for a in raw.split(",") if a.strip()
    )
    return AgentConfig(
        disabled=disabled,
        agent_timeout=float(os.getenv("AGENT_TIMEOUT", "240")),
        max_medicines=int(os.getenv("AGENT_MAX_MEDICINES", "25")),
    )
