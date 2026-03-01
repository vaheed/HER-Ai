from __future__ import annotations

from abc import ABC, abstractmethod

from her.models import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Provider interface for LLM backends."""

    name: str

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a completion for the request."""


def estimate_cost(prompt_tokens: int, completion_tokens: int, prompt_rate: float, completion_rate: float) -> float:
    """Estimate token cost in USD."""

    return round((prompt_tokens / 1000.0 * prompt_rate) + (completion_tokens / 1000.0 * completion_rate), 6)
