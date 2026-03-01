from __future__ import annotations

import httpx

from her.embeddings.base import EmbeddingProvider, normalize_dimensions
from her.providers.errors import ProviderServerError, ProviderTimeoutError


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider with compatibility for old/new APIs."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        dimensions: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * self._dimensions

        payload = {"model": self._model, "input": text}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(f"{self._base_url}/api/embed", json=payload)
                if response.status_code == 404:
                    legacy_payload = {"model": self._model, "prompt": text}
                    response = await client.post(f"{self._base_url}/api/embeddings", json=legacy_payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ollama embedding request timed out") from exc

        if response.status_code >= 500:
            raise ProviderServerError(f"Ollama embedding server error: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        vector: list[float]
        if isinstance(data.get("embedding"), list):
            vector = [float(x) for x in data["embedding"]]
        else:
            embeddings = data.get("embeddings", [])
            vector = [float(x) for x in embeddings[0]] if embeddings else []

        return normalize_dimensions(vector, self._dimensions)
