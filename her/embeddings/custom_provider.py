from __future__ import annotations

import httpx

from her.embeddings.base import EmbeddingProvider, normalize_dimensions
from her.providers.errors import ProviderAuthError, ProviderServerError, ProviderTimeoutError


class CustomEmbeddingProvider(EmbeddingProvider):
    """Custom embedding provider (OpenAI-style `input` + `model` payload)."""

    name = "custom"

    def __init__(
        self,
        endpoint: str,
        model: str,
        timeout_seconds: float,
        dimensions: int,
        api_key: str = "",
    ) -> None:
        self._endpoint = endpoint.strip()
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._dimensions = dimensions
        self._api_key = api_key

    async def embed(self, text: str) -> list[float]:
        if not self._endpoint:
            raise ProviderAuthError("Custom embedding endpoint is not configured")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {"model": self._model, "input": text}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(self._endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Custom embedding request timed out") from exc

        if response.status_code in (401, 403):
            raise ProviderAuthError("Custom embedding auth failed")
        if response.status_code >= 500:
            raise ProviderServerError(f"Custom embedding server error: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        vector = data.get("embedding")
        if vector is None:
            blocks = data.get("data", [])
            vector = blocks[0].get("embedding") if blocks else []

        return normalize_dimensions([float(x) for x in vector], self._dimensions)
