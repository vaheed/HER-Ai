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


class AnthropicProvider(LLMProvider):
    """Anthropic messages API provider implementation."""

    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._settings.anthropic_api_key:
            raise ProviderAuthError("Anthropic API key is not configured")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self._settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._settings.anthropic_model,
            "system": request.system_prompt,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Anthropic request timed out") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code == 429:
            raise ProviderRateLimitError("Anthropic rate limit")
        if response.status_code in (401, 403):
            raise ProviderAuthError("Anthropic auth failed")
        if response.status_code >= 500:
            raise ProviderServerError(f"Anthropic server error: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        cost = estimate_cost(prompt_tokens, completion_tokens, prompt_rate=0.003, completion_rate=0.015)
        text_blocks = [block.get("text", "") for block in data.get("content", [])]
        content = "\n".join(text_blocks).strip()

        return LLMResponse(
            content=content,
            provider=self.name,
            model=self._settings.anthropic_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
