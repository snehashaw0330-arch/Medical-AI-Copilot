"""Anthropic Claude provider (async), via the ``anthropic`` SDK."""

from __future__ import annotations

from backend.llm.base_llm import BaseLLM, LLMNotAvailable, LLMResponse


class ClaudeLLM(BaseLLM):
    """Anthropic Claude provider."""

    name = "claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-5",
        **options,
    ) -> None:
        super().__init__(model=model, **options)
        self.api_key = api_key
        try:
            from anthropic import AsyncAnthropic  # type: ignore

            self._client_cls = AsyncAnthropic
        except Exception:  # noqa: BLE001
            self._client_cls = None

    def available(self) -> bool:
        return bool(self.api_key and self._client_cls)

    async def acomplete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        if not self.available():
            raise LLMNotAvailable(f"{self.name}: missing API key or SDK")
        client = self._client_cls(api_key=self.api_key)
        msg = await client.messages.create(
            model=self.model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return LLMResponse(text=text.strip(), provider=self.name, model=self.model)
