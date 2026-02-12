import asyncio
from typing import Any

from crewai.tools import BaseTool

from mcp.manager import MCPManager


class MCPTool(BaseTool):
    mcp_manager: MCPManager
    server_name: str
    tool_name: str

    def _run(self, **kwargs: Any) -> str:
        try:
            return str(asyncio.run(self.mcp_manager.call_tool(self.server_name, self.tool_name, kwargs)))
        except Exception as exc:  # noqa: BLE001
            return f"MCP tool '{self.tool_name}' failed: {exc}"


class MCPToolsIntegration:
    """Convert MCP tools to CrewAI tools."""

    def __init__(self, mcp_manager: MCPManager):
        self.mcp = mcp_manager

    def create_curated_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = [
            MCPTool(
                name="web_search",
                description="Search the web for current information and sources.",
                mcp_manager=self.mcp,
                server_name="brave-search",
                tool_name="brave_web_search",
            ),
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
