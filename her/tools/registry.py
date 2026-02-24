from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict


ToolHandler = Callable[..., Awaitable[str]]


@dataclass
class Tool:
    name: str
    handler: ToolHandler
    requires_approval: bool


class ToolRegistry:
    """Registry for async tools used by the agent."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool by name."""

        self._tools[tool.name] = tool

    async def invoke(self, tool_name: str, **kwargs: str) -> str:
        """Invoke a registered tool."""

        tool = self._tools[tool_name]
        return await tool.handler(**kwargs)
