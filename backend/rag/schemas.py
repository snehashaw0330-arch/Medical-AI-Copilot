"""Pydantic models for the RAG API (the frontend contract)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- requests --------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, examples=["What is Paracetamol used for?"])
    top_k: int | None = Field(default=None, ge=1, le=20)


class MedicineInfoRequest(BaseModel):
    medicines: list[str] = Field(..., min_length=1, examples=[["Paracetamol", "Ibuprofen"]])


# --- shared sub-objects ----------------------------------------------------
class RetrievedChunkModel(BaseModel):
    text: str
    source: str
    score: float                 # 0..1 similarity
    metadata: dict[str, Any] = {}


# --- responses -------------------------------------------------------------
class QueryResponse(BaseModel):
    answer: str
    confidence: float = 0.0      # retrieval grounding confidence (0..1)
    provider: str = "offline"    # openai | gemini | offline | unavailable
    sources: list[str] = []
    chunks: list[RetrievedChunkModel] = []
    safety_note: str | None = None


class IndexResponse(BaseModel):
    indexed_chunks: int = 0
    documents: int = 0
    document_list: list[str] = []
    elapsed_seconds: float = 0.0
    vector_backend: str = ""
    embedding_model: str = ""


class StatusResponse(BaseModel):
    available: bool = False
    embedder_available: bool = False
    vector_store_available: bool = False
    indexed_chunks: int = 0
    is_indexed: bool = False
    embedding_model: str = ""
    vector_backend: str = ""
    llm_provider: str = "offline"
    documents: list[dict[str, Any]] = []
    indexed_sources: list[str] = []


class MedicineProfile(BaseModel):
    name: str
    fields: dict[str, str] = {}          # the 9 structured fields
    summary: str = ""
    confidence: float = 0.0
    sources: list[str] = []
    chunks: list[RetrievedChunkModel] = []


class InteractionReport(BaseModel):
    medicines: list[str] = []
    answer: str = ""
    confidence: float = 0.0
    sources: list[str] = []


class MedicineInfoResponse(BaseModel):
    medicines: list[MedicineProfile] = []
    interactions: InteractionReport | None = None
    provider: str = "offline"
    safety_note: str | None = None


class PrescriptionRAGResponse(BaseModel):
    """Full OCR→extract→retrieve→answer flow for an uploaded prescription."""

    extracted_medicines: list[str] = []
    ocr_provider: str | None = None
    ocr_confidence: float = 0.0
    info: MedicineInfoResponse = MedicineInfoResponse()


class UploadResponse(BaseModel):
    filename: str
    saved: bool
    reindexed: bool = False
    index: IndexResponse | None = None
