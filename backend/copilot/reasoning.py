"""Reasoning trace + activity recorder for the Copilot workflow.

The workflow (``workflow.py``) drives a fixed 11-stage pipeline. This module gives
it a single object — :class:`WorkflowTrace` — that records, for every stage:

* a :class:`ReasoningStep` (status, headline, summary, structured detail, timing),
  which powers the center-panel "AI Reasoning" view, and
* one or more :class:`ActivityEvent` entries (``09:42 OCR Completed``), which power
  the "AI Activity Timeline".

Each stage runs inside :meth:`WorkflowTrace.step`, a context manager that times the
stage and turns any exception into a ``failed`` step (best-effort: one stage never
aborts the pipeline). This keeps the orchestration in ``workflow.py`` linear and
readable while the bookkeeping lives here.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from backend.copilot.schemas import (
    ActivityEvent,
    ReasoningStep,
    StepStatus,
    utcnow,
)

logger = logging.getLogger("copilot.reasoning")


# The canonical 11-stage Copilot pipeline: (key, display name).
PIPELINE = [
    ("receive", "Receive Prescription"),
    ("ocr", "Run OCR"),
    ("extract_medicines", "Extract Medicines"),
    ("drug_interactions", "Check Drug Interactions"),
    ("disease_prediction", "Predict Disease"),
    ("evidence", "Retrieve Medical Evidence"),
    ("clinical_decision", "Generate Clinical Decision"),
    ("summary", "Generate AI Summary"),
    ("treatment", "Generate Treatment Suggestions"),
    ("follow_up", "Generate Follow-up Suggestions"),
    ("report", "Generate Final Medical Report"),
]


class WorkflowTrace:
    """Accumulates reasoning steps + activity events for one workflow run."""

    def __init__(self) -> None:
        self._steps: dict[str, ReasoningStep] = {
            key: ReasoningStep(order=i + 1, key=key, name=name)
            for i, (key, name) in enumerate(PIPELINE)
        }
        self.activity: list[ActivityEvent] = []

    # -- step lifecycle ----------------------------------------------------
    @contextmanager
    def step(self, key: str):
        """Time a stage; capture failures as a ``failed`` step (never raises)."""
        s = self._steps[key]
        s.status = StepStatus.RUNNING
        s.at = utcnow()
        t0 = time.perf_counter()
        try:
            yield s
            if s.status == StepStatus.RUNNING:
                s.status = StepStatus.COMPLETE
        except Exception as exc:  # noqa: BLE001 — one stage never breaks the run
            s.status = StepStatus.FAILED
            s.title = "Stage failed"
            s.summary = f"{s.name} could not complete: {exc}"
            logger.warning("Copilot stage '%s' failed: %s", key, exc)
        finally:
            s.duration_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    def skip(self, key: str, reason: str) -> None:
        s = self._steps[key]
        s.status = StepStatus.SKIPPED
        s.title = "Skipped"
        s.summary = reason

    # -- activity ----------------------------------------------------------
    def activity_event(
        self, label: str, *, detail: str = "",
        status: StepStatus = StepStatus.COMPLETE, step_key: str = "",
    ) -> ActivityEvent:
        """Record a timeline event (also returned so the caller can reuse it)."""
        event = ActivityEvent(label=label, detail=detail, status=status, step_key=step_key)
        self.activity.append(event)
        return event

    # -- output ------------------------------------------------------------
    def steps(self) -> list[ReasoningStep]:
        return [self._steps[key] for key, _ in PIPELINE]

    def get(self, key: str) -> ReasoningStep:
        return self._steps[key]
