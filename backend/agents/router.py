"""FastAPI routes for the Multi-Agent Medical Copilot (all async).

Endpoints
---------
* ``POST /agents/run``            — start a workflow run (background) or wait for it
* ``GET  /agents/runs``           — recent runs (for the monitor's history)
* ``GET  /agents/runs/{run_id}``  — live state of a run (polled by the monitor)
* ``GET  /agents/registry``       — agents, workflow stages + LLM providers
* ``GET  /agents/health``         — subsystem health

The upload path mirrors the existing OCR route (same allowed types, same upload
dir). Inputs are validated + sanitised (security requirement). All failures
surface as actionable HTTP errors; a run's *internal* agent failures are captured
in its state, never as a 500.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from backend.agents.agent_manager import get_manager
from backend.agents.logger import get_logger
from backend.agents.schemas import RegistryInfo, RunCreated, RunListItem, RunState
from backend.agents.security import sanitize_text, sanitize_tokens, validate_image
from backend.config import settings

logger = get_logger("router")

router = APIRouter(prefix="/agents", tags=["ai-agents"])


def _split(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").replace("\n", ",").split(",") if p.strip()]


@router.post("/run")
async def run_workflow(
    file: UploadFile | None = File(default=None),
    symptoms: str | None = Form(default=None),
    medicines: str | None = Form(default=None),
    text: str | None = Form(default=None),
    age: str | None = Form(default=None),
    gender: str | None = Form(default=None),
    diagnosis: str | None = Form(default=None),
    wait: bool = Query(default=False, description="Block until the pipeline finishes."),
) -> Any:
    """Start a multi-agent run from a prescription image and/or typed inputs."""
    inputs: dict[str, Any] = {
        "symptoms": sanitize_tokens(_split(symptoms), max_items=40),
        "medicines": sanitize_tokens(_split(medicines), max_items=25),
        "text": sanitize_text(text, max_len=5000),
        "age": sanitize_text(age, max_len=8) or None,
        "gender": sanitize_text(gender, max_len=16) or None,
        "diagnosis": sanitize_text(diagnosis, max_len=200) or None,
    }

    # Optional prescription image → validate, persist, hand ownership to the run.
    if file is not None and file.filename:
        raw = await file.read()
        ok, err = validate_image(file.filename, len(raw))
        await file.close()
        if not ok:
            raise HTTPException(status_code=400, detail=err)
        suffix = Path(file.filename).suffix.lower()
        dest = Path(settings.UPLOAD_DIR) / f"{uuid.uuid4().hex}{suffix}"
        with open(dest, "wb") as buffer:
            buffer.write(raw)
        inputs["image_path"] = str(dest)
        inputs["filename"] = file.filename
        inputs["owns_image"] = True

    manager = get_manager()
    if wait:
        state = await manager.run_and_wait(inputs)
        return state
    state = manager.start_run(inputs)
    return RunCreated(run_id=state.run_id, status=state.status, task_type=state.task_type)


@router.get("/runs", response_model=list[RunListItem])
async def list_runs(limit: int = Query(20, ge=1, le=100)) -> list[RunListItem]:
    """Recent runs (newest first) for the monitor's history panel."""
    runs = get_manager().list_runs(limit)
    return [
        RunListItem(
            run_id=r.run_id, status=r.status, task_type=r.task_type,
            created_at=r.created_at, duration_ms=r.duration_ms,
            overall_confidence=r.overall_confidence,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunState)
async def get_run(run_id: str) -> RunState:
    """Live (or final) state of a single run — polled by the monitor page."""
    state = get_manager().get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return state


@router.get("/registry", response_model=RegistryInfo)
async def registry() -> RegistryInfo:
    """Agents, the workflow diagram and the available LLM providers."""
    return get_manager().registry_info()


@router.get("/health")
async def health() -> dict:
    """Subsystem health for dashboards/ops."""
    info = get_manager().registry_info()
    return {
        "status": "ok",
        "agents": len(info.agents),
        "enabled_agents": sum(1 for a in info.agents if a.enabled),
        "llm_provider": info.llm_provider,
    }
