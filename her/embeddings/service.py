from __future__ import annotations

from typing import Optional

from her.config.settings import Settings
from her.embeddings.base import EmbeddingProvider
from her.embeddings.custom_provider import CustomEmbeddingProvider
from her.embeddings.ollama_provider import OllamaEmbeddingProvider
from her.observability.logging import get_logger


def build_embedding_provider(settings: Settings) -> Optional[EmbeddingProvider]:
    """Construct embedding provider from runtime settings."""

    provider = settings.embedding_provider.lower().strip()
    if provider == "none":
        return None
    if provider == "custom":
        return CustomEmbeddingProvider(
            endpoint=settings.custom_embedding_endpoint,
            model=settings.custom_embedding_model,
            timeout_seconds=settings.request_timeout_seconds,
            dimensions=settings.embedding_dimensions,
            api_key=settings.custom_embedding_api_key,
        )
    return OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embedding_model,
        timeout_seconds=settings.request_timeout_seconds,
        dimensions=settings.embedding_dimensions,
    )


class EmbeddingService:
    """Safe embedding facade that degrades gracefully on provider failures."""

    def __init__(self, provider: Optional[EmbeddingProvider], dimensions: int) -> None:
        self._provider = provider
        self._dimensions = dimensions
        self._logger = get_logger("embedding_service")

    async def embed(self, text: str) -> Optional[list[float]]:
        """Return embedding vector or None when embedding is unavailable."""

        if self._provider is None:
            return None
        try:
            return await self._provider.embed(text)
        except Exception as exc:
            self._logger.warning(
                "embedding_provider_failed",
                provider=self._provider.name,
                error=str(exc),
            )
            return None
