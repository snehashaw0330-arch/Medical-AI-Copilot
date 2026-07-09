"""Execution planner for the Copilot workflow.

Given what the caller actually supplied (a file? medicines? symptoms?), the
planner decides which of the 11 pipeline stages are worth running and records a
short reason for anything it chooses to skip. Keeping this decision in one place
means ``workflow.py`` stays a straight line and the skip reasons surface verbatim
in the reasoning trace.

The planner is pure and deterministic — it inspects the inputs and the runtime
feature flags, and returns a :class:`WorkflowPlan`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.config import settings


@dataclass
class WorkflowInputs:
    """Normalised description of what the caller provided."""

    has_file: bool = False
    text: str = ""
    medicines: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    diagnosis: str | None = None
    include_rag: bool = True


@dataclass
class WorkflowPlan:
    """Which stages to run, plus a reason for each skipped stage."""

    run: dict[str, bool]
    skip_reason: dict[str, str] = field(default_factory=dict)

    def should(self, key: str) -> bool:
        return self.run.get(key, False)

    def reason(self, key: str) -> str:
        return self.skip_reason.get(key, "")


def plan(inputs: WorkflowInputs) -> WorkflowPlan:
    """Decide the stage plan from the supplied inputs + feature flags."""
    run: dict[str, bool] = {}
    skip: dict[str, str] = {}

    # 1) Receive — always (even a file-less manual request "receives" its inputs).
    run["receive"] = True

    # 2) OCR — only when a file was uploaded.
    run["ocr"] = inputs.has_file
    if not inputs.has_file:
        skip["ocr"] = "No prescription image uploaded; using the supplied text/medicines."

    # 3) Extract medicines — always attempt (from OCR or the supplied list/text).
    run["extract_medicines"] = True

    # 4) Drug interactions — needs the extracted medicines (checked at runtime for
    #    the ≥2 requirement, but planned whenever any medicine could be present).
    will_have_meds = inputs.has_file or bool(inputs.medicines) or bool(inputs.text)
    run["drug_interactions"] = will_have_meds
    if not will_have_meds:
        skip["drug_interactions"] = "No medicines available to check."

    # 5) Disease prediction — needs symptoms (or a diagnosis to seed a hypothesis).
    run["disease_prediction"] = bool(inputs.symptoms) or bool(inputs.diagnosis)
    if not run["disease_prediction"]:
        skip["disease_prediction"] = "No symptoms or diagnosis supplied to predict from."

    # 6) Evidence retrieval — when RAG is enabled and requested.
    run["evidence"] = inputs.include_rag and settings.COPILOT_USE_RAG
    if not run["evidence"]:
        skip["evidence"] = (
            "Evidence retrieval disabled for this request."
            if not inputs.include_rag else "RAG knowledge base is turned off."
        )

    # 7) Clinical decision — whenever we have medicines or a disease signal.
    run["clinical_decision"] = will_have_meds or run["disease_prediction"]
    if not run["clinical_decision"]:
        skip["clinical_decision"] = "Nothing to reason over (no medicines, symptoms or diagnosis)."

    # 8-10) AI narratives — always produced (they summarise whatever ran).
    run["summary"] = True
    run["treatment"] = True
    run["follow_up"] = True

    # 11) Final report — always assembled from whatever the pipeline produced.
    run["report"] = True

    return WorkflowPlan(run=run, skip_reason=skip)
