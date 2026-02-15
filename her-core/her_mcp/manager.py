import asyncio
import contextlib
import logging
import os
import re
import shutil
from pathlib import Path
from string import Template
from typing import Any

import yaml
from utils.config_paths import resolve_config_file
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)
_UNRESOLVED_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


class MCPManager:
    """Manages MCP server lifecycle and tool execution."""

    def __init__(self, config_path: str = "mcp_servers.yaml"):
        self.config_path = resolve_config_file(config_path)
        self.config = self._load_config(self.config_path)
        self.sessions: dict[str, ClientSession] = {}
        self.tools_cache: dict[str, list[dict[str, Any]]] = {}
        self.server_status: dict[str, dict[str, str]] = {}
        self._stacks: dict[str, contextlib.AsyncExitStack] = {}
        self.startup_timeout_seconds = max(
            5,
            int(os.getenv("MCP_SERVER_START_TIMEOUT_SECONDS", "60")),
        )

    @staticmethod
    def _load_config(config_path: Path) -> dict[str, Any]:
        try:
            if not config_path.exists():
                logger.warning("MCP config not found at %s", config_path)
                return {"servers": []}
            with config_path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {"servers": []}
            if not isinstance(payload, dict):
                logger.warning("Invalid MCP config shape at %s; expected mapping", config_path)
                return {"servers": []}
            servers = payload.get("servers", [])
            if not isinstance(servers, list):
                logger.warning("Invalid MCP config servers entry at %s; expected list", config_path)
                return {"servers": []}
            return payload
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load MCP config at %s: %s", config_path, exc)
            return {"servers": []}

    def _expand_env(self, value: str) -> str:
        return Template(value).safe_substitute(os.environ)

    @staticmethod
    def _find_unresolved_placeholders(value: str) -> list[str]:
        return _UNRESOLVED_ENV_PATTERN.findall(value)

    @staticmethod
    def _normalize_legacy_stdio_args(command: str, args: list[str]) -> list[str]:
        """Remove legacy transport flags that break modern MCP server CLIs."""
        if command != "npx":
            return list(args)

        normalized: list[str] = []
        idx = 0
        while idx < len(args):
            token = args[idx]
            if token == "--transport":
                # Legacy config used "--transport stdio" for Node servers.
                # Many current MCP npm packages do not support this flag and
                # interpret it as positional input (path/URL), causing startup failures.
                next_token = args[idx + 1] if idx + 1 < len(args) else None
                if next_token == "stdio":
                    idx += 2
                    continue
                idx += 1
                continue
            normalized.append(token)
            idx += 1
        return normalized

    @staticmethod
    def _normalize_known_server_args(name: str, command: str, args: list[str]) -> list[str]:
        normalized = list(args)
        if (
            command == "npx"
            and name == "pdf"
            and "@modelcontextprotocol/server-pdf" in normalized
            and "--stdio" not in normalized
        ):
            # server-pdf defaults to HTTP mode when --stdio is missing.
            # Enforce stdio so the MCP client always receives JSON-RPC frames.
            normalized.append("--stdio")
        return normalized

    @staticmethod
    def _command_exists(command: str) -> bool:
        return shutil.which(command) is not None

    async def initialize(self):
        for server in self.config.get("servers", []):
            name = server.get("name", "unknown")
            if not server.get("enabled", False):
                self.server_status[name] = {"status": "disabled", "message": "server disabled in config"}
                continue
            try:
                await asyncio.wait_for(
                    self.start_server(name, server),
                    timeout=self.startup_timeout_seconds,
                )
            except TimeoutError:
                self.server_status[name] = {
                    "status": "failed",
                    "message": f"startup timed out after {self.startup_timeout_seconds}s",
                }
                logger.warning(
                    "MCP server '%s' startup timed out after %ss",
                    name,
                    self.startup_timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                self.server_status[name] = {"status": "failed", "message": str(exc)}
                logger.exception("MCP server '%s' failed during initialization: %s", name, exc)

    async def start_server(self, name: str, config: dict):
        stack: contextlib.AsyncExitStack | None = None
        try:
            command = config["command"]
            if not self._command_exists(command):
                self.server_status[name] = {
                    "status": "unavailable",
                    "message": f"command '{command}' is not installed; install Node.js/npm or disable this MCP server",
                }
                logger.warning("Skipping MCP server '%s': missing command '%s'", name, command)
                return

            merged_env = os.environ.copy()
            unresolved_keys: set[str] = set()
            for key, value in (config.get("env") or {}).items():
                expanded_value = self._expand_env(str(value))
                unresolved_keys.update(self._find_unresolved_placeholders(expanded_value))
                merged_env[key] = expanded_value

            # Expand env vars in args (e.g. ${POSTGRES_URL}) for servers that need URLs as CLI args
            raw_args = config.get("args", [])
            args = [self._expand_env(str(a)) for a in raw_args]
            for arg in args:
                unresolved_keys.update(self._find_unresolved_placeholders(arg))
            args = self._normalize_legacy_stdio_args(command, args)
            args = self._normalize_known_server_args(name, command, args)
            if unresolved_keys:
                missing = ", ".join(sorted(unresolved_keys))
                self.server_status[name] = {
                    "status": "unavailable",
                    "message": f"missing required environment variable(s): {missing}",
                }
                logger.warning("Skipping MCP server '%s': unresolved env placeholders: %s", name, missing)
                return

            params = StdioServerParameters(
                command=command,
                args=args,
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
        except asyncio.CancelledError as exc:
            self.server_status[name] = {"status": "failed", "message": f"startup cancelled: {exc}"}
            logger.warning("MCP server '%s' startup cancelled: %s", name, exc)
            if stack is not None:
                with contextlib.suppress(Exception):
                    await stack.aclose()
            raise
        except Exception as exc:  # noqa: BLE001
            self.server_status[name] = {"status": "failed", "message": str(exc)}
            logger.exception("Failed to start MCP server '%s'", name)
            if stack is not None:
                with contextlib.suppress(Exception):
                    await stack.aclose()

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
