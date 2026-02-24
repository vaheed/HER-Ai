from __future__ import annotations

from typing import List


class WebSocketHub:
    """Minimal websocket subscriber registry."""

    def __init__(self) -> None:
        self._clients: List[str] = []

    async def register(self, client_id: str) -> None:
        """Register a websocket client id."""

        if client_id not in self._clients:
            self._clients.append(client_id)

    async def list_clients(self) -> List[str]:
        """Return connected client ids."""

        return list(self._clients)
