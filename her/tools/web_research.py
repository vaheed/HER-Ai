from __future__ import annotations

import httpx


async def fetch_url_text(url: str, timeout_seconds: float = 10.0) -> str:
    """Fetch page text for lightweight research tasks."""

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(url)
    response.raise_for_status()
    return response.text
