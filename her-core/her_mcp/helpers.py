import json
import subprocess
from urllib.parse import quote_plus

from her_mcp.manager import MCPManager


async def web_search(mcp: MCPManager, query: str, max_results: int = 5):
    """Quick web search helper using curl (no API key required)."""
    url = (
        "https://api.duckduckgo.com/?q="
        f"{quote_plus(query)}&format=json&no_html=1&no_redirect=1"
    )

    result = subprocess.run(
        ["curl", "-fsSL", url],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    payload = json.loads(result.stdout)

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

    return "\n".join(lines[:max_results]) if lines else "Web search: no direct results"


async def read_file(mcp: MCPManager, path: str):
    """Quick file read helper."""
    return await mcp.call_tool("filesystem", "read_file", {"path": path})


async def write_file(mcp: MCPManager, path: str, content: str):
    """Quick file write helper."""
    return await mcp.call_tool(
        "filesystem",
        "write_file",
        {"path": path, "content": content},
    )
