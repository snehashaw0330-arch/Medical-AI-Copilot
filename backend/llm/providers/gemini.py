"""Google Gemini provider (async), via the ``google-generativeai`` SDK."""

from __future__ import annotations

from backend.llm.base_llm import BaseLLM, LLMNotAvailable, LLMResponse


class GeminiLLM(BaseLLM):
    """Google Gemini provider."""

    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        **options,
    ) -> None:
        super().__init__(model=model, **options)
        self.api_key = api_key
        try:
            import google.generativeai as genai  # type: ignore

            self._genai = genai
        except Exception:  # noqa: BLE001
            self._genai = None

    def available(self) -> bool:
        return bool(self.api_key and self._genai)

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
        self._genai.configure(api_key=self.api_key)
        model = self._genai.GenerativeModel(self.model, system_instruction=system)
        resp = await model.generate_content_async(
            prompt,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
        )
        return LLMResponse(text=(resp.text or "").strip(), provider=self.name, model=self.model)
