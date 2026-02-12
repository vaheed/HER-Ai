import asyncio
import contextlib
import logging
import os
from pathlib import Path
from string import Template
from typing import Any

import yaml
from utils.config_paths import resolve_config_file
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPManager:
    """Manages MCP server lifecycle and tool execution."""

    def __init__(self, config_path: str = "mcp_servers.yaml"):
        self.config_path = resolve_config_file(config_path)
        self.config = self._load_config(self.config_path)
        self.sessions: dict[str, ClientSession] = {}
        self.tools_cache: dict[str, list[dict[str, Any]]] = {}
        self.server_status: dict[str, dict[str, str]] = {}
        self._stacks: dict[str, contextlib.AsyncExitStack] = {}

    @staticmethod
    def _load_config(config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            logger.warning("MCP config not found at %s", config_path)
            return {"servers": []}
        with config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {"servers": []}

    def _expand_env(self, value: str) -> str:
        return Template(value).safe_substitute(os.environ)

    async def initialize(self):
        for server in self.config.get("servers", []):
            name = server.get("name", "unknown")
            if not server.get("enabled", False):
                self.server_status[name] = {"status": "disabled", "message": "server disabled in config"}
                continue
            await self.start_server(name, server)

    async def start_server(self, name: str, config: dict):
        try:
            merged_env = os.environ.copy()
            for key, value in (config.get("env") or {}).items():
                merged_env[key] = self._expand_env(str(value))

            params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=merged_env,
            )

            stack = contextlib.AsyncExitStack()
            read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()

            tools_result = await session.list_tools()
            tools = [self._tool_to_dict(tool) for tool in getattr(tools_result, "tools", [])]

            self.sessions[name] = session
            self.tools_cache[name] = tools
            self.server_status[name] = {"status": "running", "message": f"{len(tools)} tools loaded"}
            self._stacks[name] = stack
            logger.info("MCP server '%s' started with %s tools", name, len(tools))
        except Exception as exc:  # noqa: BLE001
            self.server_status[name] = {"status": "failed", "message": str(exc)}
            logger.exception("Failed to start MCP server '%s'", name)

    @staticmethod
    def _tool_to_dict(tool: Any) -> dict[str, Any]:
        if hasattr(tool, "model_dump"):
            return tool.model_dump()
        if isinstance(tool, dict):
            return tool
        return {
            "name": getattr(tool, "name", "unknown_tool"),
            "description": getattr(tool, "description", ""),
            "inputSchema": getattr(tool, "inputSchema", {}),
        }

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict):
        session = self.sessions.get(server_name)
        if not session:
            raise ValueError(f"MCP server '{server_name}' not available")

        result = await session.call_tool(tool_name, arguments=arguments)
        if hasattr(result, "model_dump"):
            payload = result.model_dump()
        else:
            payload = result
        return payload

    def get_all_tools(self) -> list[dict]:
        all_tools: list[dict[str, Any]] = []
        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                all_tools.append({"server": server_name, **tool})
        return all_tools

    def get_server_status(self) -> dict[str, dict]:
        return self.server_status

    async def stop_all_servers(self):
        for name, stack in list(self._stacks.items()):
            try:
                await stack.aclose()
                self.server_status[name] = {"status": "stopped", "message": "closed"}
            except Exception as exc:  # noqa: BLE001
                self.server_status[name] = {"status": "failed", "message": f"shutdown error: {exc}"}
        self._stacks.clear()
        self.sessions.clear()
        self.tools_cache.clear()

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        try:
            loop = asyncio.get_running_loop()
            raise RuntimeError("Cannot use call_tool_sync from a running event loop")
        except RuntimeError as exc:
            if "running event loop" in str(exc):
                raise
            return asyncio.run(self.call_tool(server_name, tool_name, arguments))
