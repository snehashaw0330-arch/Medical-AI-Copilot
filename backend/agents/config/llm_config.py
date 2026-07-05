"""LLM provider configuration (env-driven, no secrets in code).

Central place that decides *which* LLM the agent layer uses and with what
credentials/model. Reuses the keys already defined in ``backend/config.py``
(``OPENAI_API_KEY``, ``GEMINI_API_KEY``) and adds the rest via env, so the same
app runs locally and in the cloud without edits.

``AGENT_LLM_PROVIDER`` selects the provider:

* ``auto``   (default) — pick the first *available* provider in priority order,
  otherwise fall back to the always-on offline provider.
* ``offline`` — force the deterministic no-cloud provider.
* ``openai`` | ``gemini`` | ``claude`` | ``deepseek`` | ``ollama`` | ``future``.

This module has **no runtime dependency on the agent code**, so the LLM factory
can import it without any import cycle.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from backend.config import settings


@dataclass
class LLMConfig:
    """Resolved LLM settings for the whole agent layer."""

    provider: str = "auto"
    # Per-provider construction kwargs, passed straight to the provider __init__.
    providers: dict[str, dict] = field(default_factory=dict)
    # Priority order used when provider == "auto".
    priority: tuple[str, ...] = ("openai", "gemini", "claude", "deepseek", "ollama")


def get_llm_config() -> LLMConfig:
    """Build the LLM config from environment / existing settings."""
    provider = os.getenv("AGENT_LLM_PROVIDER", "auto").strip().lower()
    providers = {
        "openai": {
            "api_key": settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        },
        "gemini": {
            "api_key": settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY"),
            "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        },
        "claude": {
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
            "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        },
        "deepseek": {
            "api_key": os.getenv("DEEPSEEK_API_KEY"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        },
        "ollama": {
            "model": os.getenv("OLLAMA_MODEL", "llama3.1"),
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        },
    }
    return LLMConfig(provider=provider, providers=providers)
