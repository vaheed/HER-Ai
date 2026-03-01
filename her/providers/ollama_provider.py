from __future__ import annotations

import time

import httpx

from her.config.settings import Settings
from her.models import LLMRequest, LLMResponse
from her.providers.base import LLMProvider, estimate_cost
from her.providers.errors import ProviderServerError, ProviderTimeoutError


class OllamaProvider(LLMProvider):
    """Ollama local provider implementation."""

    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(self, request: LLMRequest) -> LLMResponse:
        url = f"{self._settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self._settings.ollama_model,
            "messages": [{"role": "system", "content": request.system_prompt}] + request.messages,
            "options": {
                "temperature": request.temperature,
            },
            "stream": False,
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ollama request timed out") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 500:
            raise ProviderServerError(f"Ollama server error: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content", "").strip()
        prompt_tokens = len(request.system_prompt.split()) + sum(len(m.get("content", "").split()) for m in request.messages)
        completion_tokens = len(content.split())
        cost = estimate_cost(prompt_tokens, completion_tokens, prompt_rate=0.0, completion_rate=0.0)

        return LLMResponse(
            content=content,
            provider=self.name,
            model=self._settings.ollama_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
