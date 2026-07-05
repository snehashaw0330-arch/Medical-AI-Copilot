"""Offline (no-cloud) LLM provider — the always-available safety net.

This provider needs no API key, SDK or network. It produces a deterministic,
extractive response so every agent that *optionally* uses an LLM keeps working
when no cloud/local model is configured. It never fabricates clinical facts: it
simply echoes and lightly structures the grounded text the agent already built.
"""

from __future__ import annotations

import re

from backend.llm.base_llm import BaseLLM, LLMResponse


class OfflineLLM(BaseLLM):
    """Deterministic, dependency-free fallback provider."""

    name = "offline"

    def __init__(self, model: str = "extractive-v1", **options) -> None:
        super().__init__(model=model, **options)

    def available(self) -> bool:  # always usable
        return True

    async def acomplete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        # Extractive summary: keep the most information-dense leading sentences of
        # the grounded prompt, trimmed to a sane length. No invention.
        body = prompt.strip()
        # Drop a leading instruction line if present (agents pass "Instruction:\n\n<text>").
        parts = body.split("\n\n", 1)
        content = parts[1] if len(parts) == 2 and len(parts[0]) < 200 else body
        sentences = re.split(r"(?<=[.!?])\s+", content.strip())
        summary = " ".join(s.strip() for s in sentences[:6] if s.strip())
        summary = summary[: max_tokens * 4].strip()
        if not summary:
            summary = "No additional narrative available (offline mode)."
        return LLMResponse(text=summary, provider=self.name, model=self.model)
