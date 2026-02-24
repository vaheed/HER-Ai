from __future__ import annotations

import asyncio
from typing import Dict, Iterable
from uuid import UUID

from her.models import LLMRequest, LLMResponse
from her.observability.logging import get_logger
from her.observability.metrics import record_provider_call
from her.providers.base import LLMProvider
from her.providers.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
)


RECOVERABLE_ERRORS = (
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderAuthError,
)


class FallbackRouter(LLMProvider):
    """Route a request through providers with graceful fallback."""

    name = "router"

    def __init__(self, providers: Iterable[LLMProvider], timeout_seconds: float = 30.0) -> None:
        self._providers = list(providers)
        self._timeout_seconds = timeout_seconds
        self._cache: Dict[UUID, LLMResponse] = {}
        self._logger = get_logger("fallback_router")

    async def generate(self, request: LLMRequest) -> LLMResponse:
        for provider in self._providers:
            try:
                response = await asyncio.wait_for(provider.generate(request), timeout=self._timeout_seconds)
                self._cache[request.session_id] = response
                record_provider_call(provider=provider.name, success=True, latency_ms=response.latency_ms, cost_usd=response.cost_usd)
                self._logger.info("provider_success", provider=provider.name, trace_id=request.trace_id)
                return response
            except asyncio.TimeoutError:
                self._logger.warning("provider_timeout", provider=provider.name, trace_id=request.trace_id)
                record_provider_call(provider=provider.name, success=False, latency_ms=int(self._timeout_seconds * 1000), cost_usd=0)
                continue
            except RECOVERABLE_ERRORS as exc:
                self._logger.warning(
                    "provider_recoverable_error",
                    provider=provider.name,
                    error=str(exc),
                    trace_id=request.trace_id,
                )
                record_provider_call(provider=provider.name, success=False, latency_ms=0, cost_usd=0)
                continue
            except Exception as exc:  # defensive catch around provider implementation
                self._logger.error("provider_unexpected_error", provider=provider.name, error=str(exc), trace_id=request.trace_id)
                record_provider_call(provider=provider.name, success=False, latency_ms=0, cost_usd=0)
                continue

        cached = self._cache.get(request.session_id)
        if cached:
            self._logger.warning("provider_cache_fallback", trace_id=request.trace_id)
            return LLMResponse(
                content=cached.content,
                provider="cache",
                model=cached.model,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                latency_ms=1,
            )

        raise ProviderError("All providers failed and no cached response is available")
