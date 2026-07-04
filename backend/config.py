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
