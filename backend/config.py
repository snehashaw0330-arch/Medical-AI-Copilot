"""Central configuration for the Medical AI Assistant backend.

Reads from environment variables so the same code runs locally and in
production without edits. Copy ``.env.example`` to ``.env`` and fill values,
or export the variables in your shell / deployment platform.
"""

from __future__ import annotations

import os
from pathlib import Path

# Optional: load a .env file if python-dotenv is installed. It is not required.
try:  # pragma: no cover - convenience only
    from dotenv import load_dotenv # pyright: ignore[reportMissingImports]

    load_dotenv()
except Exception:  # noqa: BLE001
    pass


# Repo root = parent of the ``backend`` package. All data paths resolve from here
# so the app behaves the same regardless of the current working directory.
ROOT_DIR = Path(__file__).resolve().parent.parent


def _path(env_value: str) -> str:
    p = Path(env_value)
    return str(p if p.is_absolute() else ROOT_DIR / p)


class Settings:
    """Runtime settings. Instantiated once as ``settings`` below."""

    # --- OCR provider selection -------------------------------------------
    # "auto" (default) uses Gemini only if GEMINI_API_KEY is set, otherwise the
    # local EasyOCR/Tesseract engine. No API key is required to run the app.
    # One of: "auto", "gemini", "openai", "google_vision", "local"
    OCR_PROVIDER: str = os.getenv("OCR_PROVIDER", "auto")

    # Gemini (optional — only used when a key is present)
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # OpenAI GPT-4o vision (alternative)
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Google Cloud Vision (alternative). Uses GOOGLE_APPLICATION_CREDENTIALS.
    GOOGLE_APPLICATION_CREDENTIALS: str | None = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )

    # --- Data + storage ----------------------------------------------------
    MEDICINE_CSV: str = _path(
        os.getenv("MEDICINE_CSV", "datasets/medicines/medicine_dataset.csv")
    )
    UPLOAD_DIR: str = _path(os.getenv("UPLOAD_DIR", "prescription-ocr/uploads"))

    # --- OCR history (persistence) ----------------------------------------
    # Async SQLAlchemy URL. Defaults to a local SQLite file; point DATABASE_URL
    # at PostgreSQL in production, e.g.
    #   postgresql+asyncpg://user:pass@host:5432/medisense
    # (no code changes required — only this env var and the asyncpg driver).
    HISTORY_DB_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{_path('backend/history/history.db')}",
    )
    # Where analyzed prescription images are retained for the history detail view.
    HISTORY_IMAGE_DIR: str = _path(
        os.getenv("HISTORY_IMAGE_DIR", "backend/history/images")
    )

    # --- Drug interaction analysis (backend/drug_interactions/) ------------
    # Knowledge source for drug–drug interactions and per-drug warnings. The
    # loader infers the backend from the file extension (.json / .csv / .db) so
    # the same setting drives CSV, JSON or SQLite without code changes. Point at
    # a remote source by setting INTERACTIONS_SOURCE (see service.build_source).
    INTERACTIONS_DATASET: str = _path(
        os.getenv("INTERACTIONS_DATASET", "datasets/drug_interactions/interactions.json")
    )
    # Optional explicit backend override: "json" | "csv" | "sqlite" | "openfda"
    # | "rxnorm" | "drugbank". "auto" (default) infers from the dataset path.
    INTERACTIONS_SOURCE: str = os.getenv("INTERACTIONS_SOURCE", "auto")
    # Persistent history of interaction analyses. Same async URL contract as the
    # OCR history store — defaults to a local SQLite file; set DATABASE_URL or
    # INTERACTIONS_DB_URL to PostgreSQL in production with no code changes.
    INTERACTIONS_DB_URL: str = os.getenv(
        "INTERACTIONS_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/drug_interactions/interactions.db')}",
        ),
    )
    # Fuzzy-match floor (0..100) for resolving an OCR'd medicine name to a known
    # drug in the dataset. Below this we treat the drug as "unknown" (no false
    # interactions are fabricated).
    INTERACTION_MATCH_THRESHOLD: float = float(
        os.getenv("INTERACTION_MATCH_THRESHOLD", "82")
    )
    # Enrich interaction reports with RAG knowledge-base context when available.
    INTERACTIONS_USE_RAG: bool = (
        os.getenv("INTERACTIONS_USE_RAG", "true").lower() == "true"
    )

    # --- Clinical Decision Support (backend/clinical_decision/) ------------
    # Persistent history of clinical analyses. Same async URL contract as the
    # other stores — defaults to a local SQLite file; set DATABASE_URL or
    # CLINICAL_DB_URL to PostgreSQL in production with no code changes.
    CLINICAL_DB_URL: str = os.getenv(
        "CLINICAL_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/clinical_decision/clinical.db')}",
        ),
    )
    # Enrich the clinical report with RAG knowledge-base context when available.
    CLINICAL_USE_RAG: bool = (
        os.getenv("CLINICAL_USE_RAG", "true").lower() == "true"
    )
    # Run disease prediction from symptoms inside the clinical analysis when no
    # disease/diagnosis is supplied by the caller.
    CLINICAL_PREDICT_DISEASE: bool = (
        os.getenv("CLINICAL_PREDICT_DISEASE", "true").lower() == "true"
    )
    # Automatically produce a clinical report after OCR when medicines are found
    # (OCR -> matching -> interactions -> RAG -> CDSS). Best-effort and non-fatal
    # by contract — a CDSS failure never blocks or breaks the OCR response.
    CLINICAL_AUTO_ON_OCR: bool = (
        os.getenv("CLINICAL_AUTO_ON_OCR", "true").lower() == "true"
    )

    # --- Medical Report Generator (backend/report_generator/) -------------
    # Persistent store of generated medical reports. Same async URL contract as
    # the other stores — defaults to a local SQLite file; set DATABASE_URL or
    # REPORTS_DB_URL to PostgreSQL in production with no code changes.
    REPORTS_DB_URL: str = os.getenv(
        "REPORTS_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/report_generator/reports.db')}",
        ),
    )
    # Where the prescription image is retained for each report (detail view + PDF).
    REPORTS_IMAGE_DIR: str = _path(
        os.getenv("REPORTS_IMAGE_DIR", "backend/report_generator/images")
    )
    # Automatically generate + store a report after every successful OCR analysis.
    # Best-effort and non-fatal by contract — a report failure never breaks OCR.
    REPORTS_AUTO_ON_OCR: bool = (
        os.getenv("REPORTS_AUTO_ON_OCR", "true").lower() == "true"
    )

    # --- Prescription Validation (backend/prescription_validation/) --------
    # Persistent history of prescription validations. Same async URL contract as
    # the other stores — defaults to a local SQLite file; set DATABASE_URL or
    # VALIDATION_DB_URL to PostgreSQL in production with no code changes.
    VALIDATION_DB_URL: str = os.getenv(
        "VALIDATION_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/prescription_validation/validation.db')}",
        ),
    )
    # Automatically validate a prescription after every successful OCR analysis.
    # Best-effort and non-fatal by contract — a validation failure never blocks
    # or breaks the OCR response.
    VALIDATION_AUTO_ON_OCR: bool = (
        os.getenv("VALIDATION_AUTO_ON_OCR", "true").lower() == "true"
    )
    # A medicine OCR'd below this row confidence (0..1) is flagged by the
    # validator's low-confidence check. Defaults to the OCR MIN_CONFIDENCE.
    VALIDATION_LOW_CONFIDENCE: float = float(
        os.getenv("VALIDATION_LOW_CONFIDENCE", os.getenv("OCR_MIN_CONFIDENCE", "0.6"))
    )

    # --- Symptom Checker & Triage (backend/symptom_checker/) ---------------
    # Persistent history of symptom-checker assessments. Same async URL contract
    # as the other stores — defaults to a local SQLite file; set DATABASE_URL or
    # SYMPTOM_DB_URL to PostgreSQL in production with no code changes.
    SYMPTOM_DB_URL: str = os.getenv(
        "SYMPTOM_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/symptom_checker/symptoms.db')}",
        ),
    )
    # Enrich triage assessments with RAG knowledge-base evidence when available.
    SYMPTOM_USE_RAG: bool = (
        os.getenv("SYMPTOM_USE_RAG", "true").lower() == "true"
    )

    # --- Medicine Recommendation (backend/medicine_recommendation/) --------
    # Persistent history of recommendation reports. Same async URL contract as
    # the other stores — defaults to a local SQLite file; set DATABASE_URL or
    # MEDICINE_REC_DB_URL to PostgreSQL in production with no code changes.
    MEDICINE_REC_DB_URL: str = os.getenv(
        "MEDICINE_REC_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/medicine_recommendation/recommendations.db')}",
        ),
    )
    # Enrich recommendation reports with RAG knowledge-base evidence when available.
    MEDICINE_REC_USE_RAG: bool = (
        os.getenv("MEDICINE_REC_USE_RAG", "true").lower() == "true"
    )
    # Automatically produce a recommendation report after every successful OCR
    # analysis when medicines are found. Best-effort and non-fatal by contract —
    # a recommendation failure never blocks or breaks the OCR response.
    MEDICINE_REC_AUTO_ON_OCR: bool = (
        os.getenv("MEDICINE_REC_AUTO_ON_OCR", "true").lower() == "true"
    )

    # --- Digital Twin (backend/digital_twin/) ------------------------------
    # Persistent per-patient twin snapshots. Same async URL contract as the other
    # stores — defaults to a local SQLite file; set DATABASE_URL or
    # DIGITAL_TWIN_DB_URL to PostgreSQL in production with no code changes. The
    # twin is *derived* live from the reports store; this only caches snapshots
    # for analytics + durability.
    DIGITAL_TWIN_DB_URL: str = os.getenv(
        "DIGITAL_TWIN_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/digital_twin/digital_twin.db')}",
        ),
    )
    # Enrich twin recommendations with RAG knowledge-base evidence when available.
    DIGITAL_TWIN_USE_RAG: bool = (
        os.getenv("DIGITAL_TWIN_USE_RAG", "true").lower() == "true"
    )

    # --- AI Governance, Audit & Explainability (backend/ai_governance/) -----
    # Persistent store of AI decision traces, audit logs and the model/dataset
    # registries. Same async URL contract as every other store — defaults to a
    # local SQLite file; set DATABASE_URL or AI_GOVERNANCE_DB_URL to PostgreSQL in
    # production with no code changes.
    AI_GOVERNANCE_DB_URL: str = os.getenv(
        "AI_GOVERNANCE_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/ai_governance/governance.db')}",
        ),
    )
    # Log every API request to the audit store via non-blocking background writes.
    GOVERNANCE_AUDIT_REQUESTS: bool = (
        os.getenv("GOVERNANCE_AUDIT_REQUESTS", "true").lower() == "true"
    )
    # Capture a live AI decision trace after every successful OCR analysis.
    # Best-effort and non-fatal by contract — a governance failure never blocks
    # or breaks the OCR response.
    GOVERNANCE_AUTO_ON_OCR: bool = (
        os.getenv("GOVERNANCE_AUTO_ON_OCR", "true").lower() == "true"
    )

    # --- Clinical Reasoning Platform (backend/clinical_reasoning/) ---------
    # Enterprise, step-by-step AI clinical reasoning that chains every existing
    # subsystem (OCR -> medicine detection/validation -> interactions -> disease
    # prediction -> RAG evidence -> clinical rules -> differential -> confidence
    # -> recommendation) and shows its full work. All flags are best-effort and
    # non-fatal by contract — a failure in any stage degrades that stage only.
    # Persistent history of reasoning reports. Same async URL contract as the
    # other stores — defaults to a local SQLite file; set DATABASE_URL or
    # CLINICAL_REASONING_DB_URL to PostgreSQL in production with no code changes.
    CLINICAL_REASONING_DB_URL: str = os.getenv(
        "CLINICAL_REASONING_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/clinical_reasoning/reasoning.db')}",
        ),
    )
    CLINICAL_REASONING_USE_RAG: bool = (
        os.getenv("CLINICAL_REASONING_USE_RAG", "true").lower() == "true"
    )
    # Run disease prediction from symptoms inside the reasoning pipeline.
    CLINICAL_REASONING_PREDICT_DISEASE: bool = (
        os.getenv("CLINICAL_REASONING_PREDICT_DISEASE", "true").lower() == "true"
    )
    # Number of differential diagnoses to consider (leading + alternatives).
    CLINICAL_REASONING_TOP_K: int = int(
        os.getenv("CLINICAL_REASONING_TOP_K", "5")
    )
    # In-memory cache of reasoning reports (keyed by a hash of the inputs). The
    # pipeline fans out to slow subsystems (disease model, RAG), so identical
    # re-runs are served from cache within the TTL. Set TTL to 0 to disable.
    CLINICAL_REASONING_CACHE_TTL: int = int(
        os.getenv("CLINICAL_REASONING_CACHE_TTL", "600")  # seconds
    )
    CLINICAL_REASONING_CACHE_SIZE: int = int(
        os.getenv("CLINICAL_REASONING_CACHE_SIZE", "128")  # max cached reports
    )

    # --- AI Medical Copilot Workspace (backend/copilot/) ------------------
    # A session-scoped orchestrator that chains every existing module — OCR ->
    # medicine extraction -> interactions -> disease prediction -> RAG evidence
    # -> clinical decision -> AI summary/treatment/follow-up -> medical report —
    # while remembering the current patient for the session. All flags are
    # best-effort and non-fatal by contract: a failure in any stage degrades that
    # stage only and never aborts the workflow.
    COPILOT_USE_RAG: bool = (
        os.getenv("COPILOT_USE_RAG", "true").lower() == "true"
    )
    # Use the provider-agnostic LLM layer for the AI summary / treatment /
    # follow-up narratives and chat. Falls back to a deterministic offline writer
    # when no provider is configured (the LLM layer is offline-safe by design).
    COPILOT_USE_LLM: bool = (
        os.getenv("COPILOT_USE_LLM", "true").lower() == "true"
    )
    # In-memory session store: how long an idle patient session is retained and
    # how many concurrent sessions to keep (LRU eviction of the oldest).
    COPILOT_SESSION_TTL: int = int(os.getenv("COPILOT_SESSION_TTL", "86400"))  # 24h
    COPILOT_MAX_SESSIONS: int = int(os.getenv("COPILOT_MAX_SESSIONS", "500"))
    # Per-session caps so memory stays bounded.
    COPILOT_MAX_MESSAGES: int = int(os.getenv("COPILOT_MAX_MESSAGES", "200"))
    COPILOT_MAX_TIMELINE: int = int(os.getenv("COPILOT_MAX_TIMELINE", "300"))
    COPILOT_MAX_ANALYSES: int = int(os.getenv("COPILOT_MAX_ANALYSES", "50"))
    # In-memory TTL+LRU cache of workflow results keyed by a hash of the inputs.
    COPILOT_CACHE_TTL: int = int(os.getenv("COPILOT_CACHE_TTL", "600"))  # seconds
    COPILOT_CACHE_SIZE: int = int(os.getenv("COPILOT_CACHE_SIZE", "128"))
    # Enrich chat with durable, cross-session patient memory (backend/patient_context/).
    # Best-effort and non-fatal by contract — a patient_context failure never
    # blocks or breaks a chat reply.
    COPILOT_USE_PATIENT_CONTEXT: bool = (
        os.getenv("COPILOT_USE_PATIENT_CONTEXT", "true").lower() == "true"
    )

    # --- Patient Context & Conversation Memory (backend/patient_context/) --
    # Durable, cross-session patient memory: OCR results, medicines, disease
    # predictions, drug interactions, reports, conversation history, AI
    # summaries and follow-up recommendations, keyed by the same slugified
    # patient_id convention as the Digital Twin. Same async URL contract as
    # every other store — defaults to a local SQLite file; set DATABASE_URL or
    # PATIENT_CONTEXT_DB_URL to PostgreSQL in production with no code changes.
    PATIENT_CONTEXT_DB_URL: str = os.getenv(
        "PATIENT_CONTEXT_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/patient_context/patient_context.db')}",
        ),
    )
    # Number of new chat messages (user + assistant) accumulated since the
    # last summary that triggers auto-summarization of the conversation.
    PATIENT_CONTEXT_SUMMARY_TRIGGER: int = int(
        os.getenv("PATIENT_CONTEXT_SUMMARY_TRIGGER", "10")
    )
    # Max items returned per event_type in the patient context detail view.
    PATIENT_CONTEXT_EVENTS_PER_TYPE: int = int(
        os.getenv("PATIENT_CONTEXT_EVENTS_PER_TYPE", "50")
    )

    # --- AI Medical Simulation Engine (backend/simulation/) ---------------
    # A "what-if" engine that lets a clinician simulate treatment/patient changes
    # (dose changes, replace/remove/add, age/weight/pregnancy/renal/hepatic/allergy)
    # and see the projected interactions, disease risk, recommendations, side
    # effects, contraindications and RAG evidence BEFORE acting. Every integration
    # is best-effort and non-fatal by contract — a failure in any stage degrades
    # that stage only and never aborts a simulation.
    SIMULATION_DB_URL: str = os.getenv(
        "SIMULATION_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/simulation/simulation.db')}",
        ),
    )
    # Retrieve knowledge-base evidence for each simulated scenario.
    SIMULATION_USE_RAG: bool = (
        os.getenv("SIMULATION_USE_RAG", "true").lower() == "true"
    )
    # Run disease prediction from symptoms inside a simulation.
    SIMULATION_PREDICT_DISEASE: bool = (
        os.getenv("SIMULATION_PREDICT_DISEASE", "true").lower() == "true"
    )
    # Maximum scenarios accepted in one simulation request (bounds fan-out).
    SIMULATION_MAX_SCENARIOS: int = int(os.getenv("SIMULATION_MAX_SCENARIOS", "6"))
    # In-memory TTL+LRU cache of simulation reports (keyed by a hash of the inputs).
    SIMULATION_CACHE_TTL: int = int(os.getenv("SIMULATION_CACHE_TTL", "600"))  # seconds
    SIMULATION_CACHE_SIZE: int = int(os.getenv("SIMULATION_CACHE_SIZE", "128"))

    # --- AI Hallucination Detection & Evidence Verification ----------------
    # (backend/evidence_verification/) Verifies any AI-generated response against
    # retrieved medical evidence: evidence coverage, citation strength, unsupported
    # claims, contradictions, a hallucination-risk category and a confidence score.
    # Every integration is best-effort and non-fatal by contract.
    VERIFICATION_DB_URL: str = os.getenv(
        "VERIFICATION_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/evidence_verification/verification.db')}",
        ),
    )
    # Reuse the RAG embedding model for semantic claim↔evidence similarity when
    # available; otherwise fall back to a deterministic lexical similarity.
    VERIFICATION_USE_EMBEDDINGS: bool = (
        os.getenv("VERIFICATION_USE_EMBEDDINGS", "true").lower() == "true"
    )
    # Number of evidence chunks to retrieve when the caller doesn't supply any.
    VERIFICATION_TOP_K: int = int(os.getenv("VERIFICATION_TOP_K", "6"))
    # Semantic cosine thresholds (MiniLM) for classifying a claim's support.
    VERIFICATION_SUPPORT_THRESHOLD: float = float(
        os.getenv("VERIFICATION_SUPPORT_THRESHOLD", "0.50")
    )
    VERIFICATION_WEAK_THRESHOLD: float = float(
        os.getenv("VERIFICATION_WEAK_THRESHOLD", "0.32")
    )
    # In-memory TTL+LRU cache of verification results (keyed by a hash of inputs).
    VERIFICATION_CACHE_TTL: int = int(os.getenv("VERIFICATION_CACHE_TTL", "600"))
    VERIFICATION_CACHE_SIZE: int = int(os.getenv("VERIFICATION_CACHE_SIZE", "256"))

    # --- Medical Document Intelligence (backend/document_intelligence/) ---
    # Generalizes intake beyond prescriptions: Blood Test / CBC / LFT / KFT /
    # Lipid Profile / Thyroid reports, Discharge Summaries and Medical
    # Certificates. Detect type -> extract text -> parse structured data ->
    # RAG -> clinical summary -> highlight abnormal findings -> AI explanation.
    # Persistent history of document analyses. Same async URL contract as the
    # other stores — defaults to a local SQLite file; set DATABASE_URL or
    # DOCUMENT_INTELLIGENCE_DB_URL to PostgreSQL in production with no code changes.
    DOCUMENT_INTELLIGENCE_DB_URL: str = os.getenv(
        "DOCUMENT_INTELLIGENCE_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/document_intelligence/document_intelligence.db')}",
        ),
    )
    # Where analyzed documents (image or PDF) are retained for the detail view.
    DOCUMENT_INTELLIGENCE_IMAGE_DIR: str = _path(
        os.getenv("DOCUMENT_INTELLIGENCE_IMAGE_DIR", "backend/document_intelligence/images")
    )
    # Enrich the clinical summary with RAG knowledge-base context when available.
    DOCUMENT_USE_RAG: bool = (
        os.getenv("DOCUMENT_USE_RAG", "true").lower() == "true"
    )
    # Use the provider-agnostic LLM layer for the clinical summary + AI
    # explanation narrative. Falls back to a deterministic, rule-based
    # composition when no provider is configured (offline-safe by design).
    DOCUMENT_USE_LLM: bool = (
        os.getenv("DOCUMENT_USE_LLM", "true").lower() == "true"
    )
    # Fuzzy-match floor (0..100) for resolving a detected lab-report row to a
    # known test in the built-in reference-range table.
    DOCUMENT_LAB_MATCH_THRESHOLD: float = float(
        os.getenv("DOCUMENT_LAB_MATCH_THRESHOLD", "80")
    )

    # --- Evidence-Based Medical Response Engine (backend/evidence_engine/) -
    # Grounds every AI-generated response in evidence retrieved from the RAG
    # knowledge base: retrieve -> rerank -> cite -> generate, with a confidence
    # score derived from evidence strength. Reuses the existing RAG retriever
    # and provider-agnostic LLM layer — no separate vector store or model.
    # Persistent history of evidence queries/chats. Same async URL contract as
    # every other store — defaults to a local SQLite file; set DATABASE_URL or
    # EVIDENCE_ENGINE_DB_URL to PostgreSQL in production with no code changes.
    EVIDENCE_ENGINE_DB_URL: str = os.getenv(
        "EVIDENCE_ENGINE_DB_URL",
        os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{_path('backend/evidence_engine/evidence_engine.db')}",
        ),
    )
    # Number of chunks retrieved from the vector store before reranking.
    EVIDENCE_ENGINE_TOP_K: int = int(os.getenv("EVIDENCE_ENGINE_TOP_K", "6"))
    # Number of chunks kept after reranking (the evidence actually cited/used
    # for generation).
    EVIDENCE_ENGINE_RERANK_TOP_K: int = int(os.getenv("EVIDENCE_ENGINE_RERANK_TOP_K", "4"))
    # Chunks below this similarity (0..1) are dropped as irrelevant.
    EVIDENCE_ENGINE_MIN_SIMILARITY: float = float(
        os.getenv("EVIDENCE_ENGINE_MIN_SIMILARITY", "0.15")
    )
    # In-memory chat session store: how long an idle session is retained and
    # how many concurrent sessions to keep (LRU eviction of the oldest).
    EVIDENCE_ENGINE_SESSION_TTL: int = int(os.getenv("EVIDENCE_ENGINE_SESSION_TTL", "3600"))
    EVIDENCE_ENGINE_MAX_SESSIONS: int = int(os.getenv("EVIDENCE_ENGINE_MAX_SESSIONS", "300"))

    # --- Pipeline tuning ---------------------------------------------------
    # A medicine match below this combined score (0-100) is flagged needs_review.
    MEDICINE_MATCH_THRESHOLD: float = float(
        os.getenv("MEDICINE_MATCH_THRESHOLD", "72")
    )
    # Below this overall confidence (0-1) we surface a "verify manually" warning.
    MIN_CONFIDENCE: float = float(os.getenv("OCR_MIN_CONFIDENCE", "0.6"))
    # Enable engine-aware preprocessing (deskew/denoise/contrast/upscale).
    ENABLE_PREPROCESSING: bool = (
        os.getenv("ENABLE_PREPROCESSING", "true").lower() == "true"
    )


settings = Settings()

# Make sure the storage directories exist at import time.
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.HISTORY_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.REPORTS_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.DOCUMENT_INTELLIGENCE_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
