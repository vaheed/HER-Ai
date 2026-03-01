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


class CustomProvider(LLMProvider):
    """Custom LLM provider using configurable endpoint and model."""

    name = "custom"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._settings.custom_llm_endpoint:
            raise ProviderAuthError("Custom LLM endpoint is not configured")

        headers = {"Content-Type": "application/json"}
        if self._settings.custom_llm_api_key:
            headers["Authorization"] = f"Bearer {self._settings.custom_llm_api_key}"

        payload = {
            "model": self._settings.custom_llm_model,
            "messages": [{"role": "system", "content": request.system_prompt}] + request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(self._settings.custom_llm_endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Custom LLM request timed out") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code == 429:
            raise ProviderRateLimitError("Custom provider rate limit")
        if response.status_code in (401, 403):
            raise ProviderAuthError("Custom provider auth failed")
        if response.status_code >= 500:
            raise ProviderServerError(f"Custom provider server error: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))

        content = ""
        choices = data.get("choices", [])
        if choices:
            content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not content:
            content = str(data.get("content", "")).strip()

        if prompt_tokens == 0:
            prompt_tokens = len(request.system_prompt.split()) + sum(
                len(message.get("content", "").split()) for message in request.messages
            )
        if completion_tokens == 0:
            completion_tokens = len(content.split())

        cost = estimate_cost(prompt_tokens, completion_tokens, prompt_rate=0.0, completion_rate=0.0)
        return LLMResponse(
            content=content,
            provider=self.name,
            model=self._settings.custom_llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
