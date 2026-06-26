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
