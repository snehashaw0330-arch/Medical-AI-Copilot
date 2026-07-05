"""DeepSeek provider — OpenAI-compatible, so it reuses the OpenAI request path.

Demonstrates the extension pattern: an OpenAI-compatible endpoint needs only a
different ``base_url`` and default model. No request logic is duplicated (DRY /
Open-Closed — we extend, we don't modify).
"""

from __future__ import annotations

from backend.llm.providers.openai import OpenAILLM


class DeepSeekLLM(OpenAILLM):
    """DeepSeek chat models via the OpenAI-compatible API."""

    name = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str | None = "https://api.deepseek.com",
        **options,
    ) -> None:
        super().__init__(api_key=api_key, model=model, base_url=base_url, **options)
