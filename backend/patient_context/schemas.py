"""Pydantic request/response contracts for Patient Context & Conversation Memory.

These are the frontend/API contract — the only shapes ``router.py`` speaks in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "ocr",
    "medicine",
    "disease_prediction",
    "interaction",
    "report",
    "chat_message",
    "summary",
    "follow_up",
]

ChatRole = Literal["user", "assistant", "system"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
class PatientContextCreateRequest(BaseModel):
    patient_name: str
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = None
    current_medicines: list[str] = Field(default_factory=list)
    known_conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    session_id: str | None = None


class PatientEventAppendRequest(BaseModel):
    """Body for ``POST /patient-context/{patientId}/events``.

    A single generic, ``event_type``-discriminated append endpoint is how
    OCR/medicine/disease/interaction/report/summary/follow-up facts actually
    get remembered — the create/read/list/delete endpoints only manage the
    profile itself.
    """

    event_type: EventType
    title: str = ""
    text: str = ""
    payload: dict = Field(default_factory=dict)
    role: ChatRole | None = None
    source_session_id: str | None = None
    source_ref_id: str | None = None
    # Only used to auto-create the profile when it doesn't exist yet.
    patient_name: str | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------
class PatientEventItem(BaseModel):
    id: str
    event_type: EventType
    role: ChatRole | None = None
    title: str = ""
    text: str = ""
    payload: dict = Field(default_factory=dict)
    source_session_id: str | None = None
    source_ref_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientContextProfile(BaseModel):
    patient_id: str
    patient_name: str
    age: int | None = None
    gender: str | None = None
    current_medicines: list[str] = Field(default_factory=list)
    known_conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    follow_up_recommendations: list[str] = Field(default_factory=list)
    last_summary: str = ""
    last_summary_at: datetime | None = None
    session_ids: list[str] = Field(default_factory=list)
    event_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientContextDetailResponse(BaseModel):
    profile: PatientContextProfile
    conversation: list[PatientEventItem] = Field(default_factory=list)
    ocr_history: list[PatientEventItem] = Field(default_factory=list)
    medicine_timeline: list[PatientEventItem] = Field(default_factory=list)
    disease_timeline: list[PatientEventItem] = Field(default_factory=list)
    interaction_history: list[PatientEventItem] = Field(default_factory=list)
    reports: list[PatientEventItem] = Field(default_factory=list)
    ai_summaries: list[PatientEventItem] = Field(default_factory=list)
    follow_ups: list[PatientEventItem] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)


class PatientContextListItem(BaseModel):
    patient_id: str
    patient_name: str
    event_count: int
    last_summary: str = ""
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientContextHistoryResponse(BaseModel):
    items: list[PatientContextListItem] = Field(default_factory=list)
    total: int = 0


class PatientContextDeleteResponse(BaseModel):
    patient_id: str
    deleted: bool
    events_removed: int = 0
