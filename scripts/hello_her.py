from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from her.config.settings import get_settings
from her.models import LLMRequest
from her.providers.anthropic_provider import AnthropicProvider
from her.providers.custom_provider import CustomProvider
from her.providers.fallback_router import FallbackRouter
from her.providers.ollama_provider import OllamaProvider
from her.providers.openai_provider import OpenAIProvider


async def main() -> None:
    """Run a local hello flow through provider fallback routing."""

    settings = get_settings()
    router = FallbackRouter(
        providers=[
            OpenAIProvider(settings),
            AnthropicProvider(settings),
            CustomProvider(settings),
            OllamaProvider(settings),
        ],
        timeout_seconds=settings.request_timeout_seconds,
    )
    response = await router.generate(
        LLMRequest(
            messages=[{"role": "user", "content": "Say hello in one short sentence."}],
            system_prompt="You are HER.",
            session_id=uuid4(),
            trace_id=str(uuid4()),
        )
    )
    print(json.dumps(response.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
