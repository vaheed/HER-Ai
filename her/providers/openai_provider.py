from __future__ import annotations

import time

import httpx

from her.config.settings import Settings
from her.models import LLMRequest, LLMResponse
from her.providers.base import LLMProvider, estimate_cost
from her.providers.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
)


class OpenAIProvider(LLMProvider):
    """OpenAI chat-completions provider implementation."""

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._settings.openai_api_key:
            raise ProviderAuthError("OpenAI API key is not configured")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._settings.openai_model,
            "messages": [{"role": "system", "content": request.system_prompt}] + request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("OpenAI request timed out") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code == 429:
            raise ProviderRateLimitError("OpenAI rate limit")
        if response.status_code in (401, 403):
            raise ProviderAuthError("OpenAI auth failed")
        if response.status_code >= 500:
            raise ProviderServerError(f"OpenAI server error: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        cost = estimate_cost(prompt_tokens, completion_tokens, prompt_rate=0.0005, completion_rate=0.0015)
        content = data["choices"][0]["message"]["content"]

        return LLMResponse(
            content=content,
            provider=self.name,
            model=self._settings.openai_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
