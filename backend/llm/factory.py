"""LLM factory — the single place that maps config → a concrete provider.

Agents call :func:`get_llm` and receive a :class:`BaseLLM`; they never import a
provider directly. Selecting/adding providers is confined to this file
(Open-Closed): register a class in ``_PROVIDERS`` and it becomes selectable.

Resolution:

* explicit provider name → that provider if available, else offline;
* ``auto`` → first available provider in the configured priority order, else offline.

The offline provider is always available, guaranteeing the app runs with no cloud
or local LLM configured.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from backend.agents.config.llm_config import LLMConfig, get_llm_config
from backend.llm.base_llm import BaseLLM
from backend.llm.providers.claude import ClaudeLLM
from backend.llm.providers.deepseek import DeepSeekLLM
from backend.llm.providers.future import FutureLLM
from backend.llm.providers.gemini import GeminiLLM
from backend.llm.providers.offline import OfflineLLM
from backend.llm.providers.ollama import OllamaLLM
from backend.llm.providers.openai import OpenAILLM

logger = logging.getLogger("agents.llm")

# Registry: provider key → class. Add new providers here only.
_PROVIDERS: dict[str, type[BaseLLM]] = {
    "openai": OpenAILLM,
    "gemini": GeminiLLM,
    "claude": ClaudeLLM,
    "deepseek": DeepSeekLLM,
    "ollama": OllamaLLM,
    "future": FutureLLM,
    "offline": OfflineLLM,
}


def _construct(name: str, cfg: LLMConfig) -> BaseLLM:
    cls = _PROVIDERS.get(name, OfflineLLM)
    kwargs = cfg.providers.get(name, {})
    try:
        return cls(**kwargs)
    except Exception:  # noqa: BLE001 — a broken provider must never crash startup
        logger.exception("Failed to construct LLM provider '%s'; using offline", name)
        return OfflineLLM()


def build_llm(cfg: LLMConfig | None = None) -> BaseLLM:
    """Resolve the configured provider to a usable :class:`BaseLLM` instance."""
    cfg = cfg or get_llm_config()

    if cfg.provider == "offline":
        return OfflineLLM()

    if cfg.provider != "auto":
        provider = _construct(cfg.provider, cfg)
        if provider.available():
            logger.info("LLM provider: %s (%s)", provider.name, provider.model)
            return provider
        logger.warning("LLM provider '%s' unavailable; falling back to offline", cfg.provider)
        return OfflineLLM()

    # auto: first available in priority order.
    for name in cfg.priority:
        provider = _construct(name, cfg)
        if provider.available():
            logger.info("LLM provider (auto): %s (%s)", provider.name, provider.model)
            return provider
    logger.info("No cloud/local LLM configured; using offline provider")
    return OfflineLLM()


@lru_cache(maxsize=1)
def get_llm() -> BaseLLM:
    """Process-wide singleton LLM (safe: providers are cheap, stateless holders)."""
    return build_llm()


def available_providers() -> dict:
    """Descriptor of every registered provider's availability (for observability)."""
    cfg = get_llm_config()
    out: dict[str, dict] = {}
    for name in _PROVIDERS:
        try:
            out[name] = _construct(name, cfg).info()
        except Exception:  # noqa: BLE001
            out[name] = {"provider": name, "available": False}
    return out
