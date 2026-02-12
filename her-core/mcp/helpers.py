from mcp.manager import MCPManager


async def web_search(mcp: MCPManager, query: str, max_results: int = 5):
    """Quick web search helper."""
    return await mcp.call_tool(
        "brave-search",
        "brave_web_search",
        {"query": query, "count": max_results},
    )


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
