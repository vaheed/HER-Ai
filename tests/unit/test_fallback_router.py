import pytest

from her.models import LLMRequest, LLMResponse
from her.providers.base import LLMProvider
from her.providers.errors import ProviderServerError
from her.providers.fallback_router import FallbackRouter
from uuid import uuid4


class FailingProvider(LLMProvider):
    name = "fail"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise ProviderServerError("failed")


class SuccessProvider(LLMProvider):
    name = "ok"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="hello",
            provider=self.name,
            model="test-model",
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.001,
            latency_ms=10,
        )


@pytest.mark.asyncio
async def test_fallback_router_uses_next_provider() -> None:
    router = FallbackRouter([FailingProvider(), SuccessProvider()], timeout_seconds=2)
    request = LLMRequest(
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="sys",
        session_id=uuid4(),
        trace_id=str(uuid4()),
    )

    response = await router.generate(request)
    assert response.provider == "ok"
    assert response.content == "hello"
