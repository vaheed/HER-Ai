import asyncio
import json
import logging
import os
import subprocess
from typing import Any
from urllib.parse import quote_plus

from langchain_core.tools import BaseTool

from her_mcp.manager import MCPManager
from her_mcp.sandbox_tools import (
    SandboxCommandTool,
    SandboxPythonTool,
    SandboxReportTool,
    SandboxTestTool,
    SandboxWebTool,
)

try:
    from her_mcp.twitter_tools import TwitterConfigTool, TwitterTool
except ImportError:
    # Twitter tools optional if tweepy not installed
    TwitterTool = None
    TwitterConfigTool = None

logger = logging.getLogger(__name__)


class CurlWebSearchTool(BaseTool):
    """No-key web search via DuckDuckGo Instant Answer API using curl or Python requests."""

    name: str = "web_search"
    description: str = "Search the web for current information and sources without API keys."

    def _run(self, query: str, max_results: int = 5, **_: Any) -> str:
        if not query.strip():
            return "Web search failed: empty query"

        url = (
            "https://api.duckduckgo.com/?q="
            f"{quote_plus(query)}&format=json&no_html=1&no_redirect=1"
        )

        # Try curl first, fallback to Python requests
        payload = None
        try:
            result = subprocess.run(
                ["curl", "-fsSL", url],
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
            )
            payload = json.loads(result.stdout)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.debug("curl failed, trying Python requests: %s", exc)
            try:
                import urllib.request
                with urllib.request.urlopen(url, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as py_exc:  # noqa: BLE001
                logger.warning("Both curl and urllib failed: %s", py_exc)
                return f"Web search failed: unable to fetch results ({exc})"
        except json.JSONDecodeError:
            return "Web search failed: invalid JSON from search endpoint"

        if not payload:
            return "Web search failed: no response"

        lines: list[str] = []
        abstract = payload.get("AbstractText")
        abstract_url = payload.get("AbstractURL")
        if abstract:
            lines.append(f"- {abstract} ({abstract_url or 'no-url'})")

        related = payload.get("RelatedTopics") or []
        for item in related:
            if len(lines) >= max_results:
                break
            if isinstance(item, dict) and item.get("Text") and item.get("FirstURL"):
                lines.append(f"- {item['Text']} ({item['FirstURL']})")
                continue
            for nested in item.get("Topics", []) if isinstance(item, dict) else []:
                if len(lines) >= max_results:
                    break
                if nested.get("Text") and nested.get("FirstURL"):
                    lines.append(f"- {nested['Text']} ({nested['FirstURL']})")

        if not lines:
            heading = payload.get("Heading") or "No direct results"
            return f"Web search: {heading}"

        return "\n".join(lines[:max_results])


class MCPTool(BaseTool):
    mcp_manager: MCPManager
    server_name: str
    tool_name: str

    def _run(self, *args: Any, **kwargs: Any) -> str:
        call_args: dict[str, Any] = dict(kwargs)

        if args:
            if len(args) == 1 and isinstance(args[0], dict) and not call_args:
                call_args = dict(args[0])
            elif len(args) == 1 and not call_args:
                call_args = {"input": args[0]}

        try:
            return str(asyncio.run(self.mcp_manager.call_tool(self.server_name, self.tool_name, call_args)))
        except Exception as exc:  # noqa: BLE001
            return f"MCP tool '{self.tool_name}' failed: {exc}"


class MCPToolsIntegration:
    """Convert MCP tools to CrewAI tools."""

    def __init__(self, mcp_manager: MCPManager):
        self.mcp = mcp_manager
        self.sandbox_container = os.getenv("SANDBOX_CONTAINER_NAME", "her-sandbox")

    def create_curated_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = [
            CurlWebSearchTool(),
            MCPTool(
                name="read_file",
                description="Read a file from the workspace filesystem.",
                mcp_manager=self.mcp,
                server_name="filesystem",
                tool_name="read_file",
            ),
            MCPTool(
                name="write_file",
                description="Write content to a file in the workspace filesystem.",
                mcp_manager=self.mcp,
                server_name="filesystem",
                tool_name="write_file",
            ),
            MCPTool(
                name="query_database",
                description="Run SQL queries against the memory PostgreSQL database.",
                mcp_manager=self.mcp,
                server_name="postgres",
                tool_name="query",
            ),
        ]

        # Add Twitter tools if available
        if TwitterTool and TwitterConfigTool:
            tools.extend([TwitterTool(), TwitterConfigTool()])

        # Add sandbox tools if Docker socket is available and sandbox container exists
        # All sandbox execution runs in the isolated 'her-sandbox' container via Docker exec
        try:
            import docker
            # Check if Docker is available and sandbox container exists
            try:
                client = docker.from_env()
                container = client.containers.get(self.sandbox_container)
                # Verify container is running
                if container.status != "running":
                    logger.warning(
                        "Sandbox container '%s' exists but is not running (status: %s)",
                        self.sandbox_container,
                        container.status,
                    )
                else:
                    # Sandbox is available and running, add tools
                    tools.extend([
                        SandboxCommandTool(container_name=self.sandbox_container),
                        SandboxPythonTool(container_name=self.sandbox_container),
                        SandboxWebTool(container_name=self.sandbox_container),
                        SandboxTestTool(container_name=self.sandbox_container),
                        SandboxReportTool(container_name=self.sandbox_container),
                    ])
                    logger.info(
                        "Sandbox tools enabled for container: %s (all execution runs in sandbox)",
                        self.sandbox_container,
                    )
            except docker.errors.NotFound:
                logger.warning(
                    "Sandbox container '%s' not found. Sandbox tools disabled.",
                    self.sandbox_container,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Sandbox container '%s' not available: %s", self.sandbox_container, exc)
        except ImportError:
            logger.debug("docker package not available, skipping sandbox tools")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Docker not available, skipping sandbox tools: %s", exc)

        if self.mcp.get_server_status().get("puppeteer", {}).get("status") == "running":
            tools.append(
                MCPTool(
                    name="navigate_browser",
                    description="Navigate a browser to a URL and return page context.",
                    mcp_manager=self.mcp,
                    server_name="puppeteer",
                    tool_name="puppeteer_navigate",
                )
            )

        return tools
