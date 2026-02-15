import asyncio
import json
import logging
import os
import socket
from pathlib import Path
import subprocess
from typing import Any
from urllib.parse import quote_plus

from langchain_core.tools import BaseTool

from her_mcp.manager import MCPManager
from her_mcp.sandbox_tools import (
    SandboxCommandTool,
    SandboxNetworkTool,
    SandboxPythonTool,
    SandboxReportTool,
    SandboxSecurityScanTool,
    SandboxTestTool,
    SandboxWebTool,
)
from utils.decision_log import DecisionLogger
from utils.decision_log import DecisionLogger

try:
    from her_mcp.twitter_tools import TwitterConfigTool, TwitterTool
except ImportError:
    # Twitter tools optional if tweepy not installed
    TwitterTool = None
    TwitterConfigTool = None

logger = logging.getLogger(__name__)
_decision_logger = DecisionLogger()


class CurlWebSearchTool(BaseTool):
    """No-key web search via DuckDuckGo Instant Answer API using curl or Python requests."""

    name: str = "web_search"
    description: str = "Search the web for current information and sources without API keys."

    def _run(self, query: str, max_results: int = 5, **_: Any) -> str:
        _decision_logger.log(
            event_type="tool_call",
            summary="web_search called",
            source="mcp_tools",
            details={"tool": "web_search", "query_preview": query[:160], "max_results": int(max_results)},
        )
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
            _decision_logger.log(
                event_type="tool_call",
                summary=f"MCP tool call {self.server_name}.{self.tool_name}",
                source="mcp_tools",
                details={
                    "tool": f"{self.server_name}.{self.tool_name}",
                    "args_preview": str(call_args)[:200],
                },
            )
            result = str(asyncio.run(self.mcp_manager.call_tool(self.server_name, self.tool_name, call_args)))
            _decision_logger.log(
                event_type="tool_result",
                summary=f"MCP tool result {self.server_name}.{self.tool_name}",
                source="mcp_tools",
                details={
                    "tool": f"{self.server_name}.{self.tool_name}",
                    "result_preview": result[:300],
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001
            return f"MCP tool '{self.tool_name}' failed: {exc}"


class MCPToolsIntegration:
    """Convert MCP tools to CrewAI tools."""

    def __init__(self, mcp_manager: MCPManager):
        self.mcp = mcp_manager
        self.sandbox_container = os.getenv("SANDBOX_CONTAINER_NAME", "her-sandbox")
        self.decision_logger = DecisionLogger()
        self.capability_status: dict[str, dict[str, str | bool]] = {
            "internet": {"available": False, "reason": "not checked"},
            "sandbox": {"available": False, "reason": "not checked"},
        }

    @staticmethod
    def _probe_internet_access() -> tuple[bool, str]:
        """Best-effort internet probe used for startup status visibility."""
        test_hosts = [("api.duckduckgo.com", 443), ("example.com", 443)]
        for host, port in test_hosts:
            try:
                with socket.create_connection((host, port), timeout=3):
                    return True, f"outbound TCP to {host}:{port} works"
            except OSError as exc:
                last_error = str(exc)
        return False, f"outbound internet probe failed: {last_error}"

    def create_curated_tools(self) -> list[BaseTool]:
        status = self.mcp.get_server_status()
        tools: list[BaseTool] = [CurlWebSearchTool()]
        tool_names: set[str] = {tools[0].name}
        internet_ok, internet_reason = self._probe_internet_access()
        self.capability_status["internet"] = {"available": internet_ok, "reason": internet_reason}
        if not internet_ok:
            logger.warning("Internet capability degraded: %s", internet_reason)
        self.decision_logger.log(
            event_type="capability_probe",
            summary=f"Internet capability {'available' if internet_ok else 'degraded'}",
            source="mcp_tools",
            details={"capability": "internet", "available": internet_ok, "reason": internet_reason},
        )

        if status.get("filesystem", {}).get("status") == "running":
            filesystem_tools = [
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
            ]
            tools.extend(filesystem_tools)
            tool_names.update(tool.name for tool in filesystem_tools)

        if status.get("postgres", {}).get("status") == "running":
            db_tool = MCPTool(
                name="query_database",
                description="Run SQL queries against the memory PostgreSQL database.",
                mcp_manager=self.mcp,
                server_name="postgres",
                tool_name="query",
            )
            tools.append(db_tool)
            tool_names.add(db_tool.name)

        # Add Twitter tools if available
        if TwitterTool and TwitterConfigTool:
            twitter_tools = [TwitterTool(), TwitterConfigTool()]
            tools.extend(twitter_tools)
            tool_names.update(tool.name for tool in twitter_tools)

        # Add sandbox tools if Docker socket is available and sandbox container exists
        # All sandbox execution runs in the isolated 'her-sandbox' container via Docker exec
        try:
            import docker
            docker_sock = Path("/var/run/docker.sock")
            if docker_sock.exists():
                try:
                    sock_gid = docker_sock.stat().st_gid
                    process_groups = os.getgroups()
                    running_as_root = os.geteuid() == 0
                    if (not running_as_root) and (sock_gid not in process_groups):
                        logger.warning(
                            "docker.sock group mismatch: socket gid=%s, process groups=%s, DOCKER_GID=%s",
                            sock_gid,
                            process_groups,
                            os.getenv("DOCKER_GID", "(unset)"),
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("docker.sock preflight check failed: %s", exc)
            # Check if Docker is available and sandbox container exists
            try:
                client = docker.from_env()
                container = client.containers.get(self.sandbox_container)
                # Verify container is running
                if container.status != "running":
                    reason = (
                        f"container '{self.sandbox_container}' present but status='{container.status}'"
                    )
                    self.capability_status["sandbox"] = {"available": False, "reason": reason}
                    logger.warning(
                        "Sandbox container '%s' exists but is not running (status: %s)",
                        self.sandbox_container,
                        container.status,
                    )
                else:
                    # Sandbox is available and running, add tools
                    sandbox_tools = [
                        SandboxCommandTool(container_name=self.sandbox_container),
                        SandboxPythonTool(container_name=self.sandbox_container),
                        SandboxWebTool(container_name=self.sandbox_container),
                        SandboxNetworkTool(container_name=self.sandbox_container),
                        SandboxSecurityScanTool(container_name=self.sandbox_container),
                        SandboxTestTool(container_name=self.sandbox_container),
                        SandboxReportTool(container_name=self.sandbox_container),
                    ]
                    tools.extend(sandbox_tools)
                    tool_names.update(tool.name for tool in sandbox_tools)
                    self.capability_status["sandbox"] = {
                        "available": True,
                        "reason": f"container '{self.sandbox_container}' is running",
                    }
                    logger.info(
                        "Sandbox tools enabled for container: %s (all execution runs in sandbox)",
                        self.sandbox_container,
                    )
            except docker.errors.NotFound:
                self.capability_status["sandbox"] = {
                    "available": False,
                    "reason": f"container '{self.sandbox_container}' not found",
                }
                logger.warning(
                    "Sandbox container '%s' not found. Sandbox tools disabled.",
                    self.sandbox_container,
                )
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if "Permission denied" in message:
                    detected_gid = None
                    try:
                        detected_gid = Path("/var/run/docker.sock").stat().st_gid
                    except Exception:  # noqa: BLE001
                        pass
                    message = (
                        f"{message}. Set DOCKER_GID to host docker.sock group id and restart compose. "
                        f"Linux: stat -c '%g' /var/run/docker.sock | macOS: stat -f '%g' /var/run/docker.sock"
                    )
                    if detected_gid is not None:
                        message += f" (detected gid: {detected_gid})"
                self.capability_status["sandbox"] = {
                    "available": False,
                    "reason": f"docker sandbox lookup failed: {message}",
                }
                logger.warning("Sandbox container '%s' not available: %s", self.sandbox_container, message)
        except ImportError:
            self.capability_status["sandbox"] = {
                "available": False,
                "reason": "python docker package not installed",
            }
            logger.debug("docker package not available, skipping sandbox tools")
        except Exception as exc:  # noqa: BLE001
            self.capability_status["sandbox"] = {
                "available": False,
                "reason": f"docker client unavailable: {exc}",
            }
            logger.warning("Docker not available, skipping sandbox tools: %s", exc)
        self.decision_logger.log(
            event_type="capability_probe",
            summary=(
                "Sandbox capability "
                f"{'available' if bool((self.capability_status.get('sandbox') or {}).get('available')) else 'degraded'}"
            ),
            source="mcp_tools",
            details={
                "capability": "sandbox",
                "available": bool((self.capability_status.get("sandbox") or {}).get("available")),
                "reason": str((self.capability_status.get("sandbox") or {}).get("reason", "")),
            },
        )

        if self.mcp.get_server_status().get("puppeteer", {}).get("status") == "running":
            browser_tool = MCPTool(
                name="navigate_browser",
                description="Navigate a browser to a URL and return page context.",
                mcp_manager=self.mcp,
                server_name="puppeteer",
                tool_name="puppeteer_navigate",
            )
            tools.append(browser_tool)
            tool_names.add(browser_tool.name)

        # Add all discovered MCP tools as namespaced tools so agents can access
        # broader capabilities (network, docs, memory, pdf, reasoning, etc.).
        for tool_meta in self.mcp.get_all_tools():
            server_name = str(tool_meta.get("server", "")).strip()
            raw_tool_name = str(tool_meta.get("name", "")).strip()
            if not server_name or not raw_tool_name:
                continue

            namespaced_name = f"mcp_{server_name}_{raw_tool_name}".replace("-", "_")
            if namespaced_name in tool_names:
                continue

            description = (
                str(tool_meta.get("description", "")).strip()
                or f"Execute MCP tool '{raw_tool_name}' from server '{server_name}'."
            )
            dynamic_tool = MCPTool(
                name=namespaced_name,
                description=description,
                mcp_manager=self.mcp,
                server_name=server_name,
                tool_name=raw_tool_name,
            )
            tools.append(dynamic_tool)
            tool_names.add(namespaced_name)

        return tools

    def get_capability_status(self) -> dict[str, dict[str, str | bool]]:
        return dict(self.capability_status)
