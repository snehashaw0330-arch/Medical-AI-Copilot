"""Version manager — the single source of truth for every AI component version.

Enterprise AI governance requires that **every** decision be reproducible: given
the same input and the same versions, the pipeline must yield the same output.
That is only possible if the versions of each moving part are pinned and stamped
onto every trace. This module centralises those version identifiers so the whole
platform agrees on one answer to "which model / dataset / prompt / pipeline / RAG
index produced this decision?".

Versions are read from the environment first (so a deployment can pin exact
values without code changes) and fall back to sensible, descriptive defaults.
Nothing here performs I/O — it is a pure, import-safe registry of constants that
the tracer, registries and dashboard all reference.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Bump these defaults when the underlying artefact materially changes. In
# production, override via the matching environment variable so the running
# system reports the exact pinned version without a code deploy.
_DEFAULTS: dict[str, str] = {
    "model_version": "disease-predictor-v1.4.0",
    "ocr_model_version": "ocr-ensemble-v2.1.0",
    "medicine_matcher_version": "medicine-matcher-v1.2.0",
    "interaction_model_version": "ddi-analyzer-v1.1.0",
    "clinical_model_version": "cdss-rules-v1.3.0",
    "dataset_version": "medicines-2024.11",
    "prompt_version": "prompt-lib-v1.5.0",
    "pipeline_version": "pipeline-v3.0.0",
    "rag_index_version": "kb-index-v2.2.0",
}

_ENV_KEYS: dict[str, str] = {
    "model_version": "GOV_MODEL_VERSION",
    "ocr_model_version": "GOV_OCR_MODEL_VERSION",
    "medicine_matcher_version": "GOV_MEDICINE_MATCHER_VERSION",
    "interaction_model_version": "GOV_INTERACTION_MODEL_VERSION",
    "clinical_model_version": "GOV_CLINICAL_MODEL_VERSION",
    "dataset_version": "GOV_DATASET_VERSION",
    "prompt_version": "GOV_PROMPT_VERSION",
    "pipeline_version": "GOV_PIPELINE_VERSION",
    "rag_index_version": "GOV_RAG_INDEX_VERSION",
}


@dataclass(frozen=True)
class VersionSet:
    """An immutable snapshot of every component version at trace time."""

    model_version: str
    ocr_model_version: str
    medicine_matcher_version: str
    interaction_model_version: str
    clinical_model_version: str
    dataset_version: str
    prompt_version: str
    pipeline_version: str
    rag_index_version: str

    def as_dict(self) -> dict[str, str]:
        return {
            "model_version": self.model_version,
            "ocr_model_version": self.ocr_model_version,
            "medicine_matcher_version": self.medicine_matcher_version,
            "interaction_model_version": self.interaction_model_version,
            "clinical_model_version": self.clinical_model_version,
            "dataset_version": self.dataset_version,
            "prompt_version": self.prompt_version,
            "pipeline_version": self.pipeline_version,
            "rag_index_version": self.rag_index_version,
        }


class VersionManager:
    """Resolves and serves the current version set (env-overridable)."""

    def _resolve(self, key: str) -> str:
        return os.getenv(_ENV_KEYS[key], _DEFAULTS[key])

    def current(self) -> VersionSet:
        """The version set to stamp onto a new decision trace."""
        return VersionSet(**{k: self._resolve(k) for k in _DEFAULTS})

    def as_dict(self) -> dict[str, str]:
        return self.current().as_dict()


_MANAGER: VersionManager | None = None


def get_version_manager() -> VersionManager:
    """Process-wide singleton accessor (dependency-injection friendly)."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = VersionManager()
    return _MANAGER
