# MCP Integration Guide for HER

> Complete guide to integrating Model Context Protocol (MCP) into the HER AI Assistant system

## 🎯 Why MCP for HER?

The Model Context Protocol is the **perfect replacement** for custom tools because:

1. **Industry Standard**: Adopted by OpenAI, Anthropic, Google DeepMind, Microsoft
2. **1000+ Pre-built Servers**: Community-maintained integrations ready to use
3. **No Custom Code**: Replace weeks of development with configuration
4. **Universal Protocol**: Works with any LLM (OpenAI, Groq, Claude)
5. **Better Than Custom Tools**: More reliable, tested, and maintained

## 📦 What MCP Replaces in HER

| Old Approach | New MCP Approach | Benefit |
|--------------|------------------|---------|
| Custom Ubuntu sandbox container | `@modelcontextprotocol/server-puppeteer` | No Docker overhead |
| Custom web search tool | `@modelcontextprotocol/server-brave-search` | Professional API |
| Custom code executor | MCP code-interpreter servers | Sandboxed by default |
| Custom file operations | `@modelcontextprotocol/server-filesystem` | Standard protocol |
| Future integrations | Browse 1000+ MCP servers | Instant access |

## 🚀 Quick Start


## 📌 Current Repository Implementation (Phase 2 scaffolding)

The repository currently includes a concrete MCP implementation used by startup wiring:

- `her-core/mcp/manager.py`
  - Loads `config/mcp_servers.yaml`
  - Starts enabled MCP servers
  - Caches tool metadata
  - Exposes `call_tool()`, `get_all_tools()`, and `get_server_status()`
- `her-core/mcp/tools.py`
  - Wraps curated MCP actions as CrewAI tools (`web_search`, `read_file`, `write_file`, `query_database`, optional `navigate_browser`)
- `her-core/mcp/helpers.py`
  - Async convenience wrappers for web/file operations
- `her-core/main.py`
  - Initializes MCP manager at startup and injects curated tools into the conversation agent

Default MCP profile in this repo: `config/mcp_servers.yaml`

- Enabled by default: `brave-search`, `filesystem`, `postgres`, `memory`
- Disabled by default: `puppeteer`

Required environment variables for this profile are documented in `.env.example`:
`BRAVE_API_KEY`, `POSTGRES_URL`.

## ✅ Ready-to-use local MCP profile

This repository now ships a free local MCP profile at:

- `config/mcp_servers.local.yaml`

It is designed for out-of-the-box use (no API keys) with:
- `@modelcontextprotocol/server-filesystem`
- `mcp-fetch-server`
- `@modelcontextprotocol/server-memory`
- `@modelcontextprotocol/server-sequential-thinking`
- `@modelcontextprotocol/server-pdf`

The `sandbox/Dockerfile` pre-installs these server packages globally so startup is faster
and agents can use them immediately.

### 1. Install MCP Python SDK

```bash
# In her-core container
pip install mcp
```

### 2. Create MCP Configuration

```yaml
# config/mcp_servers.yaml

servers:
  # Essential servers for HER
  - name: brave-search
    enabled: true
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-brave-search"
    env:
      BRAVE_API_KEY: "${BRAVE_API_KEY}"
    description: "Web search capabilities"
  
  - name: filesystem
    enabled: true
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-filesystem"
      - /workspace
    env: {}
    description: "Read/write files in workspace"
  
  - name: postgres
    enabled: true
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-postgres"
    env:
      DATABASE_URL: "${POSTGRES_URL}"
    description: "Query HER's memory database"
  
  - name: memory
    enabled: true
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-memory"
    env: {}
    description: "Knowledge graph for context"
  
  - name: puppeteer
    enabled: false
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-puppeteer"
    env: {}
    description: "Browser automation for complex tasks"
```

### 3. Implement MCP Manager

```python
# her-core/mcp/manager.py

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import yaml
import os
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class MCPManager:
    """
    Central manager for all MCP server connections in HER.
    Handles lifecycle, tool discovery, and execution.
    """
    
    def __init__(self, config_path: str = "config/mcp_servers.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.servers: Dict[str, dict] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self.tools_cache: Dict[str, List] = {}
        self._initialized = False
    
    def _load_config(self) -> dict:
        """Load MCP server configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {self.config_path} not found, using defaults")
            return {'servers': []}
    
    async def initialize(self):
        """Initialize all configured MCP servers"""
        if self._initialized:
            logger.warning("MCP Manager already initialized")
            return
        
        logger.info("Initializing MCP Manager...")
        await self.start_all_servers()
        self._initialized = True
        logger.info(f"MCP Manager initialized with {len(self.servers)} servers")
    
    async def start_all_servers(self):
        """Start all enabled MCP servers from config"""
        for server_config in self.config.get('servers', []):
            if server_config.get('enabled', True):
                await self.start_server(
                    server_config['name'],
                    server_config
                )
    
    async def start_server(self, name: str, config: dict):
        """
        Start a single MCP server
        
        Args:
            name: Server identifier
            config: Server configuration dict
        """
        try:
            # Prepare environment variables
            env = {**os.environ}
            for key, value in config.get('env', {}).items():
                # Expand environment variables in config
                if value.startswith('${') and value.endswith('}'):
                    env_var = value[2:-1]
                    env[key] = os.getenv(env_var, '')
                else:
                    env[key] = value
            
            # Create server parameters
            server_params = StdioServerParameters(
                command=config['command'],
                args=config.get('args', []),
                env=env
            )
            
            logger.info(f"Starting MCP server: {name}")
            
            # Start server and create session
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize session
                    init_result = await session.initialize()
                    
                    # Store session (keep it alive)
                    self.sessions[name] = session
                    
                    # Discover tools
                    tools_result = await session.list_tools()
                    tools = tools_result.tools if tools_result else []
                    
                    # Cache tools
                    self.tools_cache[name] = tools
                    
                    # Store server info
                    self.servers[name] = {
                        'config': config,
                        'session': session,
                        'tools': tools,
                        'status': 'running',
                        'description': config.get('description', ''),
                        'capabilities': init_result.capabilities if init_result else {}
                    }
                    
                    logger.info(
                        f"✓ Started '{name}' with {len(tools)} tools: "
                        f"{', '.join([t.name for t in tools[:3]])}"
                        f"{'...' if len(tools) > 3 else ''}"
                    )
                    
                    return tools
                    
        except Exception as e:
            logger.error(f"✗ Failed to start MCP server '{name}': {e}")
            self.servers[name] = {
                'config': config,
                'status': 'failed',
                'error': str(e)
            }
            return []
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Call a tool from an MCP server
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Tool arguments as dict
        
        Returns:
            Tool execution result
        
        Raises:
            ValueError: If server not running
            Exception: If tool execution fails
        """
        if server_name not in self.sessions:
            raise ValueError(
                f"Server '{server_name}' not running. "
                f"Available: {list(self.sessions.keys())}"
            )
        
        session = self.sessions[server_name]
        args = arguments or {}
        
        try:
            logger.debug(f"Calling {server_name}.{tool_name}({args})")
            result = await session.call_tool(tool_name, args)
            logger.debug(f"Result: {result.content[:100]}...")
            return result.content
        except Exception as e:
            logger.error(f"Error calling {server_name}.{tool_name}: {e}")
            raise
    
    def get_all_tools(self) -> List[dict]:
        """Get all available tools from all running servers"""
        all_tools = []
        for server_name, server_info in self.servers.items():
            if server_info.get('status') == 'running':
                for tool in server_info.get('tools', []):
                    all_tools.append({
                        'server': server_name,
                        'name': tool.name,
                        'full_name': f"{server_name}_{tool.name}",
                        'description': tool.description,
                        'parameters': tool.inputSchema
                    })
        return all_tools
    
    def get_tools_for_server(self, server_name: str) -> List[dict]:
        """Get tools for a specific server"""
        if server_name not in self.servers:
            return []
        
        server_info = self.servers[server_name]
        if server_info.get('status') != 'running':
            return []
        
        return [
            {
                'name': tool.name,
                'description': tool.description,
                'parameters': tool.inputSchema
            }
            for tool in server_info.get('tools', [])
        ]
    
    def get_server_status(self) -> Dict[str, dict]:
        """Get status of all MCP servers"""
        status = {}
        for name, info in self.servers.items():
            status[name] = {
                'status': info.get('status', 'unknown'),
                'description': info.get('description', ''),
                'tools_count': len(info.get('tools', [])),
                'error': info.get('error'),
                'tools': [t.name for t in info.get('tools', [])]
            }
        return status
    
    async def stop_all_servers(self):
        """Gracefully stop all MCP servers"""
        logger.info("Stopping all MCP servers...")
        for name in list(self.sessions.keys()):
            await self.stop_server(name)
        self._initialized = False
    
    async def stop_server(self, name: str):
        """Stop a single MCP server"""
        if name in self.sessions:
            try:
                # Close session
                session = self.sessions[name]
                # await session.close()  # Implement if available
                del self.sessions[name]
                
                # Update status
                if name in self.servers:
                    self.servers[name]['status'] = 'stopped'
                
                logger.info(f"✓ Stopped MCP server '{name}'")
            except Exception as e:
                logger.error(f"Error stopping server '{name}': {e}")
    
    async def reload_server(self, name: str):
        """Reload a specific MCP server"""
        if name in self.servers:
            config = self.servers[name].get('config')
            if config:
                await self.stop_server(name)
                await self.start_server(name, config)
                logger.info(f"Reloaded MCP server '{name}'")


# Singleton instance
_mcp_manager: Optional[MCPManager] = None

def get_mcp_manager() -> MCPManager:
    """Get or create the global MCP manager instance"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


# Helper functions for common operations

async def web_search(query: str, max_results: int = 5) -> str:
    """Perform web search via MCP"""
    mcp = get_mcp_manager()
    result = await mcp.call_tool(
        'brave-search',
        'brave_web_search',
        {'query': query, 'count': max_results}
    )
    return result

async def execute_code(code: str, language: str = 'python') -> str:
    """Execute code via MCP code interpreter"""
    mcp = get_mcp_manager()
    result = await mcp.call_tool(
        'code-interpreter',
        'execute',
        {'code': code, 'language': language}
    )
    return result

async def read_file(path: str) -> str:
    """Read file via MCP filesystem"""
    mcp = get_mcp_manager()
    result = await mcp.call_tool(
        'filesystem',
        'read_file',
        {'path': path}
    )
    return result

async def write_file(path: str, content: str) -> str:
    """Write file via MCP filesystem"""
    mcp = get_mcp_manager()
    result = await mcp.call_tool(
        'filesystem',
        'write_file',
        {'path': path, 'content': content}
    )
    return result
```

### 4. Integrate with CrewAI

```python
# her-core/agents/mcp_tools.py

from crewai import Tool
from mcp.manager import get_mcp_manager
import asyncio
from typing import List, Callable
import logging

logger = logging.getLogger(__name__)

class MCPToolsIntegration:
    """Converts MCP tools to CrewAI Tool format"""
    
    def __init__(self):
        self.mcp = get_mcp_manager()
    
    async def initialize(self):
        """Initialize MCP manager"""
        await self.mcp.initialize()
    
    def create_crewai_tools(self) -> List[Tool]:
        """
        Dynamically create CrewAI tools from all MCP servers
        
        Returns:
            List of CrewAI Tool objects
        """
        tools = []
        
        for tool_info in self.mcp.get_all_tools():
            server = tool_info['server']
            name = tool_info['name']
            full_name = tool_info['full_name']
            description = tool_info['description']
            parameters = tool_info['parameters']
            
            # Create wrapper function for each tool
            def create_tool_func(srv, tname):
                def tool_func(**kwargs):
                    try:
                        result = asyncio.run(
                            self.mcp.call_tool(srv, tname, kwargs)
                        )
                        return result
                    except Exception as e:
                        logger.error(f"Tool {srv}.{tname} failed: {e}")
                        return f"Error: {str(e)}"
                return tool_func
            
            # Create CrewAI tool
            crewai_tool = Tool(
                name=full_name,
                description=f"[{server}] {description}",
                func=create_tool_func(server, name)
            )
            
            tools.append(crewai_tool)
            logger.debug(f"Created CrewAI tool: {full_name}")
        
        logger.info(f"Created {len(tools)} CrewAI tools from MCP servers")
        return tools
    
    def create_curated_tools(self) -> List[Tool]:
        """
        Create a curated list of essential tools for HER
        (Recommended for better performance)
        """
        return [
            # Web Search
            Tool(
                name="web_search",
                description="Search the web for current information. Use when user asks about recent events, news, or things you don't know.",
                func=lambda query: asyncio.run(
                    self.mcp.call_tool(
                        'brave-search',
                        'brave_web_search',
                        {'query': query, 'count': 5}
                    )
                )
            ),
            
            # Memory Query (PostgreSQL)
            Tool(
                name="query_memories",
                description="Query HER's long-term memory database to recall past conversations and user preferences.",
                func=lambda query: asyncio.run(
                    self.mcp.call_tool(
                        'postgres',
                        'query',
                        {'sql': query}
                    )
                )
            ),
            
            # File Read
            Tool(
                name="read_file",
                description="Read the contents of a file from the workspace.",
                func=lambda path: asyncio.run(
                    self.mcp.call_tool(
                        'filesystem',
                        'read_file',
                        {'path': path}
                    )
                )
            ),
            
            # File Write
            Tool(
                name="write_file",
                description="Write content to a file in the workspace.",
                func=lambda path, content: asyncio.run(
                    self.mcp.call_tool(
                        'filesystem',
                        'write_file',
                        {'path': path, 'content': content}
                    )
                )
            ),
            
            # Browser Automation
            Tool(
                name="browser_navigate",
                description="Open a webpage in a browser and extract information.",
                func=lambda url: asyncio.run(
                    self.mcp.call_tool(
                        'puppeteer',
                        'navigate',
                        {'url': url}
                    )
                )
            ),
        ]
```

### 5. Update Main Application

```python
# her-core/main.py

import asyncio
from mcp.manager import get_mcp_manager
from agents.mcp_tools import MCPToolsIntegration
from agents.conversation_agent import ConversationAgent
from telegram.bot import HERBot
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting HER AI Assistant...")
    
    # Initialize MCP
    logger.info("Initializing MCP servers...")
    mcp_tools = MCPToolsIntegration()
    await mcp_tools.initialize()
    
    # Get MCP status
    mcp = get_mcp_manager()
    status = mcp.get_server_status()
    logger.info(f"MCP Status: {status}")
    
    # Create tools for agents
    tools = mcp_tools.create_curated_tools()
    logger.info(f"Created {len(tools)} tools for agents")
    
    # Initialize conversation agent with MCP tools
    conversation_agent = ConversationAgent(tools=tools)
    
    # Start Telegram bot
    bot = HERBot(conversation_agent)
    await bot.start()
    
    logger.info("HER is now running!")
    
    try:
        # Keep running
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await mcp.stop_all_servers()
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## 🎨 Recommended MCP Servers for HER

### Essential (Always Enable)
1. **`@modelcontextprotocol/server-brave-search`** - Web search
2. **`@modelcontextprotocol/server-filesystem`** - File operations
3. **`@modelcontextprotocol/server-postgres`** - Memory queries
4. **`@modelcontextprotocol/server-memory`** - Knowledge graph

### Recommended (Enable Based on Needs)
5. **`@modelcontextprotocol/server-puppeteer`** - Browser automation
6. **`@modelcontextprotocol/server-github`** - GitHub integration
7. **`@modelcontextprotocol/server-slack`** - Slack communication
8. **`@modelcontextprotocol/server-google-drive`** - Cloud storage

### Optional (Advanced Features)
9. **`@modelcontextprotocol/server-sequential-thinking`** - Enhanced reasoning
10. **`@hyperbrowser/mcp-server-hyperbrowser`** - Advanced browser control
11. **`@modelcontextprotocol/server-playwright`** - Alternative browser
12. **`@executeautomation/mcp-server-docker`** - Docker management

## 🔧 Configuration Examples

### Minimal Configuration (Fastest)
```yaml
servers:
  - name: brave-search
    enabled: true
    command: npx
    args: ["-y", "@modelcontextprotocol/server-brave-search"]
    env:
      BRAVE_API_KEY: "${BRAVE_API_KEY}"
```

### Production Configuration (Recommended)
```yaml
servers:
  - name: brave-search
    enabled: true
    command: npx
    args: ["-y", "@modelcontextprotocol/server-brave-search"]
    env:
      BRAVE_API_KEY: "${BRAVE_API_KEY}"
    description: "Web search for current information"
  
  - name: filesystem
    enabled: true
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    env: {}
    description: "Workspace file management"
  
  - name: postgres
    enabled: true
    command: npx
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: "${POSTGRES_URL}"
    description: "Query HER's memory database"
  
  - name: memory
    enabled: true
    command: npx
    args: ["-y", "@modelcontextprotocol/server-memory"]
    env: {}
    description: "Knowledge graph for contextual memory"
  
  - name: puppeteer
    enabled: false
    command: npx
    args: ["-y", "@modelcontextprotocol/server-puppeteer"]
    env: {}
    description: "Browser automation for complex web tasks"
```

## 📊 Benefits Summary

| Metric | Before (Custom Tools) | After (MCP) | Improvement |
|--------|----------------------|-------------|-------------|
| **Development Time** | 2-3 weeks | 1-2 days | 90% faster |
| **Code Maintenance** | High | Low | Outsourced to community |
| **Tool Reliability** | Variable | High | Battle-tested |
| **Available Integrations** | ~5-10 | 1000+ | 100x more |
| **Container Overhead** | +1 sandbox container | None | Resource savings |
| **Security** | Custom implementation | Industry standard | More secure |
| **Documentation** | Must write own | Community docs | Better |

## 🚀 Next Steps

1. **Week 5 of Roadmap**: Replace custom tools with MCP
2. **Test each MCP server** individually before production
3. **Monitor performance** - MCP adds minimal overhead
4. **Expand integrations** - Browse awesome-mcp-servers for more
5. **Custom MCP servers** - Build your own if needed

## 🔗 Resources

- **MCP Official Docs**: https://modelcontextprotocol.io
- **Awesome MCP Servers**: https://github.com/punkpeye/awesome-mcp-servers
- **MCP Python SDK**: https://github.com/modelcontextprotocol/python-sdk
- **MCP Specification**: https://spec.modelcontextprotocol.io

---

**Last Updated**: 2025-02-07  
**MCP Version**: 2025-11-25  
**Python SDK**: Latest