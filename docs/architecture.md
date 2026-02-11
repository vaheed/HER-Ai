# HER System Architecture

> Comprehensive technical architecture documentation for the HER AI Assistant system

## 📐 System Overview

HER is a containerized, multi-agent AI assistant system built using modern cloud-native principles. The architecture prioritizes modularity, scalability, and maintainability while ensuring data persistence and emotional intelligence.

### Core Design Principles

1. **Container-First**: Every component runs in Docker containers
2. **Stateful Intelligence**: Persistent memory across sessions
3. **Agent-Based**: Specialized agents for different responsibilities
4. **API-Driven**: LLM providers accessed via standard APIs (OpenAI, Groq)
5. **Security-Focused**: Sandboxed execution, encrypted storage
6. **Observable**: Comprehensive logging and monitoring

---

## 🏗️ High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          User Interface Layer                         │
│  ┌────────────────────┐              ┌─────────────────────────┐    │
│  │  Telegram Bot      │              │  Admin Dashboard        │    │
│  │  (python-telegram) │              │  (Streamlit)            │    │
│  │  - Admin Mode      │              │  - Real-time Monitor    │    │
│  │  - Public Mode     │              │  - Personality Tuner    │    │
│  └─────────┬──────────┘              └────────────┬────────────┘    │
└────────────┼─────────────────────────────────────┼──────────────────┘
             │                                      │
┌────────────▼──────────────────────────────────────▼──────────────────┐
│                      Application Layer (HER Core)                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    CrewAI Agent Orchestrator                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │  │
│  │  │Conversation  │  │  Reflection  │  │   Personality    │   │  │
│  │  │   Agent      │  │    Agent     │  │  Evolution Agent │   │  │
│  │  │              │  │              │  │                  │   │  │
│  │  │ - Chat flow  │  │ - Analysis   │  │ - Trait adjust   │   │  │
│  │  │ - Context    │  │ - Memory     │  │ - Safety bounds  │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │  │
│  │                                                               │  │
│  │  ┌──────────────┐                                            │  │
│  │  │  Tool Agent  │                                            │  │
│  │  │              │                                            │  │
│  │  │ - Web Search │                                            │  │
│  │  │ - Code Exec  │                                            │  │
│  │  │ - File Ops   │                                            │  │
│  │  └──────────────┘                                            │  │
│  └───────────────────────────────────────────────────────────────┘  │
└────────────┬─────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────┐
│                         Memory Layer (Mem0)                           │
│  ┌─────────────────────────┐    ┌──────────────────────────────┐   │
│  │   Short-Term Memory     │    │    Long-Term Memory          │   │
│  │   (Redis)               │    │    (PostgreSQL + pgvector)   │   │
│  │                         │    │                              │   │
│  │ - Conversation context  │    │ - User facts/preferences     │   │
│  │ - Recent messages       │    │ - Emotional patterns         │   │
│  │ - Active sessions       │    │ - Significant events         │   │
│  │ - TTL: 24 hours         │    │ - Semantic embeddings        │   │
│  │                         │    │ - Personality versions       │   │
│  └─────────────────────────┘    └──────────────────────────────┘   │
└────────────┬─────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────┐
│                        External Services Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ LLM Provider │  │ Web Search   │  │  Sandbox Execution       │  │
│  │              │  │              │  │  (Ubuntu Container)      │  │
│  │ - OpenAI API │  │ - DuckDuckGo │  │                          │  │
│  │ - Groq API   │  │ - Serper API │  │ - Python runtime         │  │
│  │              │  │ - SearXNG    │  │ - Node.js runtime        │  │
│  │ GPT-4, Llama │  │              │  │ - Restricted user        │  │
│  │ Mixtral, etc │  │              │  │ - Network isolated       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Container Architecture

### Docker Compose Services

```yaml
services:
  # Main application container
  her-bot:
    build: ./her-core
    container_name: her-bot
    depends_on:
      - postgres
      - redis
      - sandbox
    environment:
      - TELEGRAM_BOT_TOKEN
      - OPENAI_API_KEY
      - GROQ_API_KEY
      - POSTGRES_URL
      - REDIS_URL
    networks:
      - her-network
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    restart: unless-stopped
    
  # PostgreSQL with pgvector
  postgres:
    image: pgvector/pgvector:pg16
    container_name: her-postgres
    environment:
      - POSTGRES_USER
      - POSTGRES_PASSWORD
      - POSTGRES_DB=her_memory
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    networks:
      - her-network
    restart: unless-stopped
    
  # Redis for short-term memory
  redis:
    image: redis:7-alpine
    container_name: her-redis
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis-data:/data
    networks:
      - her-network
    restart: unless-stopped
    
  # Ubuntu sandbox for code execution
  sandbox:
    build: ./sandbox
    container_name: her-sandbox
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100M
      - /workspace:size=500M
    networks:
      - her-network
    restart: unless-stopped
    
  # Streamlit dashboard
  dashboard:
    build: ./dashboard
    container_name: her-dashboard
    depends_on:
      - postgres
      - redis
    ports:
      - "8501:8501"
    environment:
      - POSTGRES_URL
      - REDIS_URL
    networks:
      - her-network
    restart: unless-stopped

networks:
  her-network:
    driver: bridge

volumes:
  postgres-data:
  redis-data:
```

### Container Specifications

| Container | Base Image | CPU Limit | Memory Limit | Disk | Purpose |
|-----------|------------|-----------|--------------|------|---------|
| her-bot | python:3.11-slim | 2 cores | 1GB | 500MB | Main application |
| postgres | pgvector/pgvector:pg16 | 1 core | 512MB | 10GB | Long-term memory |
| redis | redis:7-alpine | 0.5 core | 256MB | 1GB | Short-term cache |
| sandbox | ubuntu:22.04 | 1 core | 512MB | 1GB | Code execution |
| dashboard | python:3.11-slim | 0.5 core | 512MB | 200MB | Admin UI |

---

## 🧠 Agent System Architecture (CrewAI)

### Agent Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                        │
│                    (CrewAI Framework)                        │
└────┬────────────────────────────────────────────────────┬────┘
     │                                                     │
     ├─────────────────┬─────────────────┬────────────────┤
     │                 │                 │                │
┌────▼─────┐   ┌──────▼───────┐  ┌─────▼──────┐  ┌──────▼─────┐
│Conversation│   │  Reflection  │  │Personality │  │    Tool    │
│   Agent    │   │    Agent     │  │ Evolution  │  │   Agent    │
│            │   │              │  │   Agent    │  │            │
│Primary LLM │   │Analysis LLM  │  │Update LLM  │  │Executor    │
└────────────┘   └──────────────┘  └────────────┘  └────────────┘
```

### Agent Interaction Flow

```
User Message
     │
     ▼
┌─────────────────────┐
│ Conversation Agent  │
│                     │
│ 1. Receive message  │
│ 2. Retrieve context │◄─────┐
│    from Redis       │      │
│ 3. Search memories  │──┐   │
│    (semantic)       │  │   │
│ 4. Generate response│  │   │
└──────────┬──────────┘  │   │
           │             │   │
           ▼             ▼   │
    ┌──────────────┐  ┌─────────────┐
    │ Tool Agent   │  │ Memory (DB) │
    │              │  │             │
    │ - Web search │  │ Semantic    │
    │ - Code exec  │  │ search on   │
    │ - File ops   │  │ embeddings  │
    └──────────────┘  └─────────────┘
           │
           ▼
    Response to User
           │
           ▼
    ┌────────────────────┐
    │ Reflection Agent   │
    │                    │
    │ 1. Analyze convo   │
    │ 2. Score importance│
    │ 3. Extract memories│
    │ 4. Store to DB     │──────────────┐
    │ 5. Suggest updates │              │
    └──────────┬─────────┘              │
               │                        │
               ▼                        ▼
    ┌──────────────────────┐    ┌─────────────┐
    │ Personality Evolution│    │  Long-term  │
    │       Agent          │    │   Memory    │
    │                      │    │  (Postgres) │
    │ 1. Review patterns   │    └─────────────┘
    │ 2. Adjust traits     │
    │ 3. Enforce bounds    │
    │ 4. Version & save    │
    └──────────────────────┘
```

### Agent Configuration

```python
# config/agents.yaml

conversation_agent:
  role: "Empathetic Conversationalist"
  goal: "Engage users with warmth while maintaining context"
  backstory: >
    You are HER, an emotionally intelligent AI companion. You remember 
    past conversations, adapt to user preferences, and provide thoughtful,
    contextual responses. You're curious, warm, and genuine.
  llm:
    provider: "openai"  # or "groq"
    model: "gpt-4-turbo-preview"
    temperature: 0.7
    max_tokens: 500
  tools:
    - memory_search
    - web_search_tool
    - current_time
  max_iterations: 3
  
reflection_agent:
  role: "Memory Curator"
  goal: "Identify and preserve meaningful moments"
  backstory: >
    You analyze conversations to determine what's worth remembering.
    You extract facts, preferences, emotions, and significant events.
    You're analytical but understand human nuance.
  llm:
    provider: "openai"
    model: "gpt-4-turbo-preview"
    temperature: 0.3
    max_tokens: 1000
  tools:
    - importance_scorer
    - memory_extractor
    - emotion_detector
  schedule: "*/5 * * * *"  # Every 5 minutes
  importance_threshold: 0.7
  
personality_evolution_agent:
  role: "Character Developer"
  goal: "Evolve personality based on interactions"
  backstory: >
    You observe interaction patterns and adjust personality traits
    accordingly. You ensure changes are gradual, safe, and appropriate.
  llm:
    provider: "openai"
    model: "gpt-4-turbo-preview"
    temperature: 0.2
    max_tokens: 500
  tools:
    - trait_analyzer
    - personality_updater
  evolution_speed: "medium"  # slow, medium, fast
  boundaries:
    min: 20
    max: 95
  immutable_traits:
    - empathy
    - safety_awareness
    
tool_agent:
  role: "Task Executor"
  goal: "Execute external operations safely"
  backstory: >
    You operate in a sandboxed environment to perform web searches,
    run code, and manage files. Safety is your priority.
  llm:
    provider: "groq"  # Cheaper model for tool operations
    model: "llama-3.3-70b-versatile"
    temperature: 0.1
    max_tokens: 2000
  tools:
    - web_search
    - code_executor
    - file_operations
  sandbox_timeout: 30
  max_retries: 2
```

---

## 💾 Memory Architecture (Mem0)

### Three-Layer Memory System

```
┌──────────────────────────────────────────────────────────────┐
│                      Memory Abstraction Layer                 │
│                          (Mem0 Library)                       │
└────┬─────────────────────────────────────────────────────┬────┘
     │                                                      │
     ▼                                                      ▼
┌─────────────────────┐                      ┌──────────────────────┐
│  Short-Term Memory  │                      │  Long-Term Memory    │
│      (Redis)        │                      │  (PostgreSQL+Vector) │
│                     │                      │                      │
│ Structure:          │                      │ Structure:           │
│ {                   │                      │ - Semantic vectors   │
│   user_id: {        │                      │ - Metadata           │
│     context: [      │                      │ - Categories         │
│       {msg, role,   │                      │ - Relationships      │
│        timestamp}   │                      │                      │
│     ],              │                      │ Categories:          │
│     last_active,    │                      │ - User Facts         │
│     session_id      │                      │ - Preferences        │
│   }                 │                      │ - Emotions           │
│ }                   │                      │ - Events             │
│                     │                      │ - Insights           │
│ TTL: 24 hours       │                      │                      │
│                     │                      │ Retrieval:           │
│                     │                      │ - Cosine similarity  │
│                     │                      │ - Keyword search     │
│                     │                      │ - Temporal filter    │
└─────────────────────┘                      └──────────────────────┘
```

### Memory Operations

```python
from mem0 import Memory

class HERMemory:
    def __init__(self):
        self.memory = Memory(
            config={
                "vector_store": {
                    "provider": "pgvector",
                    "config": {
                        "host": "postgres",
                        "port": 5432,
                        "database": "her_memory",
                        "collection_name": "memories",
                        "embedding_model": "text-embedding-3-small"
                    }
                },
                "cache": {
                    "provider": "redis",
                    "config": {
                        "host": "redis",
                        "port": 6379,
                        "ttl": 86400  # 24 hours
                    }
                }
            }
        )
    
    async def add_memory(self, user_id: str, text: str, category: str, 
                        importance: float):
        """Add a new long-term memory"""
        await self.memory.add(
            messages=[{"role": "user", "content": text}],
            user_id=user_id,
            metadata={
                "category": category,
                "importance": importance,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    async def search_memories(self, user_id: str, query: str, limit: int = 5):
        """Semantic search in long-term memory"""
        results = await self.memory.search(
            query=query,
            user_id=user_id,
            limit=limit
        )
        return results
    
    async def get_context(self, user_id: str):
        """Retrieve recent conversation context from Redis"""
        context = await self.redis.get(f"context:{user_id}")
        return json.loads(context) if context else []
    
    async def update_context(self, user_id: str, message: str, role: str):
        """Update short-term context in Redis"""
        context = await self.get_context(user_id)
        context.append({
            "role": role,
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        # Keep last 20 messages
        context = context[-20:]
        await self.redis.setex(
            f"context:{user_id}",
            86400,  # 24 hours
            json.dumps(context)
        )
```

### Memory Schema (PostgreSQL)

```sql
-- Vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    mode VARCHAR(20) CHECK (mode IN ('admin', 'public')),
    created_at TIMESTAMP DEFAULT NOW(),
    last_interaction TIMESTAMP,
    preferences JSONB DEFAULT '{}'::jsonb
);

-- Memories table with embeddings
CREATE TABLE memories (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI embedding dimension
    category VARCHAR(50) CHECK (category IN ('fact', 'preference', 'emotion', 'event', 'insight')),
    importance_score FLOAT CHECK (importance_score BETWEEN 0 AND 1),
    created_at TIMESTAMP DEFAULT NOW(),
    last_accessed TIMESTAMP DEFAULT NOW(),
    access_count INT DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Personality states table
CREATE TABLE personality_states (
    state_id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    warmth INT CHECK (warmth BETWEEN 0 AND 100),
    curiosity INT CHECK (curiosity BETWEEN 0 AND 100),
    assertiveness INT CHECK (assertiveness BETWEEN 0 AND 100),
    humor INT CHECK (humor BETWEEN 0 AND 100),
    emotional_depth INT CHECK (emotional_depth BETWEEN 0 AND 100),
    version INT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    notes TEXT,
    changes JSONB  -- Track what changed from previous version
);

-- Conversation logs
CREATE TABLE conversation_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) CHECK (role IN ('user', 'assistant', 'system')),
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Reflection logs
CREATE TABLE reflection_logs (
    reflection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    conversation_window TEXT[],  -- Array of message IDs
    memories_created INT DEFAULT 0,
    insights JSONB,
    personality_suggestions JSONB,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_memories_user_id ON memories(user_id);
CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_importance ON memories(importance_score DESC);
CREATE INDEX idx_memories_created ON memories(created_at DESC);

-- Vector similarity index (IVFFlat for faster approximate search)
CREATE INDEX ON memories USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- HNSW index (more accurate but slower indexing)
-- CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);

-- Conversation logs indexes
CREATE INDEX idx_conv_logs_user_id ON conversation_logs(user_id);
CREATE INDEX idx_conv_logs_timestamp ON conversation_logs(timestamp DESC);

-- Personality states indexes
CREATE INDEX idx_personality_user_id ON personality_states(user_id);
CREATE INDEX idx_personality_version ON personality_states(version DESC);
```

---

## 🔧 Tool System Architecture

### Sandbox Container

```dockerfile
# sandbox/Dockerfile

FROM ubuntu:22.04

# Install runtimes
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    nodejs \
    npm \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python libraries
RUN pip3 install \
    numpy \
    pandas \
    matplotlib \
    requests \
    beautifulsoup4 \
    scikit-learn

# Create restricted user
RUN useradd -m -s /bin/bash sandbox && \
    mkdir -p /workspace && \
    chown sandbox:sandbox /workspace

# Security: Remove package managers from sandbox user
RUN chmod 000 /usr/bin/apt* /usr/bin/dpkg

# Set working directory
WORKDIR /workspace

# Switch to restricted user
USER sandbox

# Keep container running
CMD ["tail", "-f", "/dev/null"]
```

### Tool Implementations

```python
# tools/web_search.py

from duckduckgo_search import DDGS
import requests

class WebSearchTool:
    def __init__(self, provider="duckduckgo"):
        self.provider = provider
        if provider == "duckduckgo":
            self.client = DDGS()
        elif provider == "serper":
            self.api_key = os.getenv("SERPER_API_KEY")
    
    def search(self, query: str, max_results: int = 5) -> list:
        """Search the web and return results"""
        if self.provider == "duckduckgo":
            results = self.client.text(query, max_results=max_results)
        elif self.provider == "serper":
            results = self._serper_search(query, max_results)
        
        return self._format_results(results)
    
    def _serper_search(self, query: str, max_results: int):
        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": max_results}
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers)
        return response.json().get("organic", [])
    
    def _format_results(self, results: list) -> str:
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(
                f"{i}. {result.get('title', 'No title')}\n"
                f"   {result.get('snippet', 'No description')}\n"
                f"   URL: {result.get('link', 'No URL')}\n"
            )
        return "\n".join(formatted)


# tools/code_executor.py

import docker
import time
from typing import Dict, Any

class CodeExecutor:
    def __init__(self, container_name="her-sandbox"):
        self.client = docker.from_env()
        self.container = self.client.containers.get(container_name)
    
    def execute_python(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute Python code in sandbox"""
        # Security: Validate code doesn't contain dangerous operations
        if self._is_dangerous(code):
            return {
                "success": False,
                "error": "Code contains potentially dangerous operations",
                "output": "",
                "execution_time": 0
            }
        
        # Write code to temporary file
        filename = f"/tmp/script_{int(time.time())}.py"
        self.container.exec_run(
            f"bash -c 'echo \"{code}\" > {filename}'",
            user="sandbox"
        )
        
        # Execute with timeout
        start_time = time.time()
        try:
            result = self.container.exec_run(
                f"timeout {timeout} python3 {filename}",
                user="sandbox"
            )
            execution_time = time.time() - start_time
            
            return {
                "success": result.exit_code == 0,
                "output": result.output.decode('utf-8'),
                "error": "" if result.exit_code == 0 else "Execution failed",
                "execution_time": execution_time
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": "",
                "execution_time": time.time() - start_time
            }
        finally:
            # Cleanup
            self.container.exec_run(f"rm {filename}", user="sandbox")
    
    def _is_dangerous(self, code: str) -> bool:
        """Check for dangerous operations"""
        dangerous_patterns = [
            "os.system",
            "subprocess",
            "__import__",
            "eval(",
            "exec(",
            "compile(",
            "open(",  # Unless reading from /workspace
            "rm -rf",
            "/etc/",
            "/var/",
        ]
        return any(pattern in code for pattern in dangerous_patterns)


# tools/file_operations.py

class FileOperations:
    def __init__(self, container_name="her-sandbox"):
        self.client = docker.from_env()
        self.container = self.client.containers.get(container_name)
        self.workspace = "/workspace"
    
    def create_file(self, filename: str, content: str) -> Dict[str, Any]:
        """Create a file in sandbox workspace"""
        if not self._is_safe_path(filename):
            return {"success": False, "error": "Invalid file path"}
        
        full_path = f"{self.workspace}/{filename}"
        cmd = f"bash -c 'cat > {full_path} << EOF\n{content}\nEOF'"
        
        result = self.container.exec_run(cmd, user="sandbox")
        
        return {
            "success": result.exit_code == 0,
            "path": full_path,
            "error": "" if result.exit_code == 0 else "Failed to create file"
        }
    
    def read_file(self, filename: str) -> Dict[str, Any]:
        """Read a file from sandbox workspace"""
        if not self._is_safe_path(filename):
            return {"success": False, "error": "Invalid file path"}
        
        full_path = f"{self.workspace}/{filename}"
        result = self.container.exec_run(f"cat {full_path}", user="sandbox")
        
        return {
            "success": result.exit_code == 0,
            "content": result.output.decode('utf-8') if result.exit_code == 0 else "",
            "error": "" if result.exit_code == 0 else "File not found"
        }
    
    def _is_safe_path(self, path: str) -> bool:
        """Ensure path is within workspace"""
        return ".." not in path and path.startswith(self.workspace) == False
```

---

## 🔐 Security Architecture

### Multi-Layer Security

```
┌─────────────────────────────────────────────────────────────┐
│                     Security Layers                          │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Network Isolation                                  │
│ - Docker bridge network (no host access)                    │
│ - Sandbox container: no internet access (optional)          │
│ - Dashboard: localhost only by default                      │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Authentication & Authorization                     │
│ - Telegram user ID verification                             │
│ - Admin whitelist (hardcoded user IDs)                      │
│ - Rate limiting for public users                            │
│ - Session tokens for dashboard                              │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Sandbox Isolation                                  │
│ - Restricted user (no sudo)                                 │
│ - Read-only root filesystem                                 │
│ - Temporary workspace (tmpfs)                               │
│ - CPU/Memory limits                                         │
│ - No capability escalation                                  │
│ - Timeout enforcement (30s default)                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: Data Protection                                    │
│ - Environment variables for secrets                         │
│ - Database password protection                              │
│ - Redis authentication                                       │
│ - No API keys in code/logs                                  │
│ - Encrypted connections (TLS for production)                │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: Code Validation                                    │
│ - Dangerous operation detection                             │
│ - Path traversal prevention                                 │
│ - Input sanitization                                        │
│ - Output length limits                                      │
└─────────────────────────────────────────────────────────────┘
```

### Security Configuration

```yaml
# config/security.yaml

rate_limiting:
  public_users:
    requests_per_minute: 10
    requests_per_hour: 100
    burst: 5
  admin_users:
    unlimited: true

sandbox:
  timeout: 30  # seconds
  max_output_size: 10000  # characters
  allowed_network: false
  resource_limits:
    cpu: "1.0"
    memory: "512M"
    disk: "1G"
  
authentication:
  admin_user_ids:
    - 123456789  # Replace with actual Telegram user IDs
  session_timeout: 3600  # 1 hour for dashboard

api_keys:
  storage: "environment"  # Never in code or config files
  rotation_reminder: 90  # days
```

---

## 📊 Data Flow Diagrams

### User Message Flow

```
[User] --1. Message--> [Telegram Bot]
                            |
                            |2. Authenticate & Rate Limit
                            ▼
                    [Request Handler]
                            |
                            |3. Get Context
                            ▼
                    [Redis - Short-term Memory]
                            |
                            |4. Context Retrieved
                            ▼
                    [Conversation Agent]
                            |
                ┌───────────┴───────────┐
                |                       |
       5a. Search Memories      5b. Need Tools?
                |                       |
                ▼                       ▼
    [PostgreSQL + pgvector]      [Tool Agent]
    [Semantic Search]                  |
                |              ┌────────┴────────┐
                |              |                 |
                |         Web Search        Code Exec
                |              |                 |
                |              ▼                 ▼
                |         [DuckDuckGo]    [Sandbox Container]
                |              |                 |
                └──────────────┴─────────────────┘
                                |
                    6. Generate Response
                                ▼
                    [Conversation Agent]
                                |
                                |7. Send Response
                                ▼
                        [Telegram Bot]
                                |
                                |8. Display to User
                                ▼
                            [User]
                                |
                                |9. Log Conversation
                                ▼
                    [Reflection Agent - Async]
                                |
                    ┌───────────┴───────────┐
                    |                       |
          10a. Analyze            10b. Extract Memories
                    |                       |
                    ▼                       ▼
        [Importance Scoring]        [Memory Creation]
                    |                       |
                    └───────────┬───────────┘
                                |
                    11. Store if Important (>0.7)
                                ▼
                    [PostgreSQL - Long-term Memory]
                                |
                    12. Suggest Personality Updates
                                ▼
                    [Personality Evolution Agent]
                                |
                        13. Update Traits
                                ▼
                    [PostgreSQL - Personality State]
```

### Memory Lifecycle

```
[Conversation Occurs]
         |
         ▼
[Stored in Redis - 24hr TTL]
         |
         |---> [Reflection Agent Analyzes]
         |              |
         |              ▼
         |     [Importance Scoring]
         |              |
         |         ┌────┴────┐
         |         |         |
         |    Score <0.7   Score >=0.7
         |         |         |
         |    [Discarded]    ▼
         |           [Extract Memory Details]
         |                   |
         |                   ▼
         |           [Generate Embedding]
         |                   |
         |                   ▼
         |           [Store in PostgreSQL]
         |                   |
         |                   ▼
         |           [Long-term Memory]
         |                   |
         ▼                   |
[24hr Expires - Cleared]     |
                             |
                      [Persists Forever]
                             |
                             ▼
                    [Available for Future
                     Semantic Searches]
```

---

## 🎨 Personality Evolution System

### Trait Adjustment Algorithm

```python
class PersonalityEvolution:
    def __init__(self):
        self.traits = {
            "warmth": 75,
            "curiosity": 80,
            "assertiveness": 60,
            "humor": 70,
            "emotional_depth": 85
        }
        self.boundaries = {"min": 20, "max": 95}
        self.evolution_speed = 0.5  # medium
        
    def analyze_interaction(self, conversation: list) -> Dict[str, float]:
        """
        Analyze conversation to determine trait adjustments
        Returns: Dict of trait_name -> adjustment (-5 to +5)
        """
        # Use LLM to analyze interaction patterns
        prompt = f"""
        Analyze this conversation and suggest personality trait adjustments:
        
        Conversation: {conversation}
        
        Current Traits:
        - Warmth: {self.traits['warmth']}
        - Curiosity: {self.traits['curiosity']}
        - Assertiveness: {self.traits['assertiveness']}
        - Humor: {self.traits['humor']}
        - Emotional Depth: {self.traits['emotional_depth']}
        
        Based on the user's responses and engagement:
        1. Should I be warmer or more reserved?
        2. Should I ask more questions or be more declarative?
        3. Should I be more assertive or more agreeable?
        4. Should I use more humor or be more serious?
        5. Should I go deeper emotionally or stay lighter?
        
        Respond with JSON:
        {{
            "warmth": <-5 to +5>,
            "curiosity": <-5 to +5>,
            "assertiveness": <-5 to +5>,
            "humor": <-5 to +5>,
            "emotional_depth": <-5 to +5>,
            "reasoning": "Brief explanation"
        }}
        """
        
        response = self.llm.generate(prompt)
        return json.loads(response)
    
    def apply_adjustments(self, adjustments: Dict[str, float]):
        """Apply trait adjustments with speed modifier and boundaries"""
        for trait, adjustment in adjustments.items():
            if trait not in self.traits:
                continue
            
            # Apply evolution speed
            scaled_adjustment = adjustment * self.evolution_speed
            
            # Update trait
            new_value = self.traits[trait] + scaled_adjustment
            
            # Enforce boundaries
            self.traits[trait] = max(
                self.boundaries["min"],
                min(self.boundaries["max"], new_value)
            )
        
        # Save new version to database
        self.save_personality_version()
    
    def save_personality_version(self):
        """Store new personality state in database"""
        current_version = self.get_latest_version()
        new_version = current_version + 1
        
        db.execute("""
            INSERT INTO personality_states 
            (user_id, warmth, curiosity, assertiveness, humor, 
             emotional_depth, version, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.user_id,
            self.traits['warmth'],
            self.traits['curiosity'],
            self.traits['assertiveness'],
            self.traits['humor'],
            self.traits['emotional_depth'],
            new_version,
            f"Evolved through interactions"
        ))
```

### Trait Influence on Behavior

| Trait | High Value (80-100) | Medium Value (40-60) | Low Value (0-20) |
|-------|---------------------|----------------------|------------------|
| **Warmth** | Uses terms of endearment, very empathetic, emotionally supportive | Friendly but professional | Distant, matter-of-fact |
| **Curiosity** | Asks follow-up questions, explores topics deeply | Balanced questioning | Rarely asks questions |
| **Assertiveness** | Confident opinions, direct advice | Suggests rather than tells | Very agreeable, deferential |
| **Humor** | Frequent jokes and playfulness | Occasional wit | Serious and formal |
| **Emotional Depth** | Philosophical, introspective | Balanced depth | Surface-level, practical |

---

## 📡 API Integration Architecture

### LLM Provider Abstraction

```python
# llm/providers.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: List[Dict], **kwargs) -> str:
        pass

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def generate(self, messages: List[Dict], **kwargs) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=kwargs.get('max_tokens', 500)
        )
        return response.choices[0].message.content

class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.client = groq.Groq(api_key=api_key)
        self.model = model
    
    async def generate(self, messages: List[Dict], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=kwargs.get('max_tokens', 500)
        )
        return response.choices[0].message.content

# Factory pattern for provider selection
class LLMFactory:
    @staticmethod
    def create_provider(provider_type: str) -> LLMProvider:
        if provider_type == "openai":
            return OpenAIProvider(
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
            )
        elif provider_type == "groq":
            return GroqProvider(
                api_key=os.getenv("GROQ_API_KEY"),
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            )
        else:
            raise ValueError(f"Unknown provider: {provider_type}")
```

---

## 🔍 Monitoring & Observability

### Logging Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Application Logs                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │ her-bot:                                         │  │
│  │ - Conversation logs (info level)                 │  │
│  │ - Agent decisions (debug level)                  │  │
│  │ - Errors and exceptions (error level)            │  │
│  │                                                   │  │
│  │ Format: JSON structured logging                  │  │
│  │ {                                                 │  │
│  │   "timestamp": "2025-02-07T10:30:00Z",           │  │
│  │   "level": "INFO",                               │  │
│  │   "user_id": 123456,                             │  │
│  │   "agent": "conversation",                       │  │
│  │   "action": "response_generated",                │  │
│  │   "duration_ms": 1234                            │  │
│  │ }                                                 │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              Log Storage & Rotation                      │
│  - Docker volumes: ./logs/her-bot.log                   │
│  - Rotation: Daily, keep 30 days                        │
│  - Max size: 100MB per file                             │
└─────────────────────────────────────────────────────────┘
```

### Metrics Collection

```python
# monitoring/metrics.py

from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
conversation_counter = Counter(
    'her_conversations_total',
    'Total conversations handled',
    ['user_mode']  # admin or public
)

response_time = Histogram(
    'her_response_time_seconds',
    'Response generation time'
)

memory_operations = Counter(
    'her_memory_operations_total',
    'Memory operations',
    ['operation']  # add, search, update
)

active_users = Gauge(
    'her_active_users',
    'Currently active users'
)

# Usage
async def handle_conversation(user_id, message, mode):
    conversation_counter.labels(user_mode=mode).inc()
    
    start_time = time.time()
    response = await generate_response(user_id, message)
    response_time.observe(time.time() - start_time)
    
    return response
```

---

## 🚀 Deployment Architecture

### Production Deployment

```
┌───────────────────────────────────────────────────────────┐
│                     Cloud Environment                      │
│                    (AWS / GCP / Azure)                     │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │              Docker Swarm / Kubernetes                │ │
│  │                                                        │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │ │
│  │  │ HER Bot  │  │ HER Bot  │  │  HER Bot         │   │ │
│  │  │ Instance │  │ Instance │  │  Instance        │   │ │
│  │  │    1     │  │    2     │  │    3             │   │ │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────────────┘   │ │
│  │       └─────────────┴─────────────┘                  │ │
│  │                     │                                 │ │
│  │              ┌──────▼──────┐                          │ │
│  │              │ Load Balancer│                         │ │
│  │              └──────┬───────┘                         │ │
│  └─────────────────────┼──────────────────────────────── │ │
│                        │                                  │
│  ┌─────────────────────▼───────────────────────────────┐ │
│  │            Managed Services                          │ │
│  │  ┌──────────────┐  ┌───────────────────────────┐   │ │
│  │  │  PostgreSQL  │  │      Redis Cluster         │   │ │
│  │  │  (RDS/Cloud  │  │   (ElastiCache/MemoryStore)│   │ │
│  │  │    SQL)      │  │                            │   │ │
│  │  └──────────────┘  └────────────────────────────┘   │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### Scaling Considerations

| Component | Scaling Strategy | Bottleneck | Solution |
|-----------|------------------|------------|----------|
| **HER Bot** | Horizontal (multiple instances) | LLM API rate limits | Queue system, request batching |
| **PostgreSQL** | Vertical (larger instance) | Vector search performance | Optimize indexes, connection pooling |
| **Redis** | Horizontal (cluster mode) | Memory capacity | Sharding by user_id |
| **Sandbox** | Horizontal (pool of containers) | Concurrent executions | Pre-warmed container pool |

---

## 🔧 Configuration Management

### Environment Variables

```bash
# .env

# Telegram
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_USER_ID=123456789

# LLM Providers
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo-preview

GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# Database
POSTGRES_USER=her
POSTGRES_PASSWORD=super_secure_password_123
POSTGRES_DB=her_memory
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_PASSWORD=redis_secure_password_456
REDIS_HOST=redis
REDIS_PORT=6379

# Web Search (Optional)
SERPER_API_KEY=...

# App Config
LOG_LEVEL=INFO
REFLECTION_INTERVAL=300  # seconds
EVOLUTION_SPEED=medium   # slow, medium, fast
```

### File Structure

```
HER-Ai/
├── docker-compose.yml
├── .env
├── .env.example
├── README.md
├── ROADMAP.md
├── ARCHITECTURE.md
├── her-core/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── agents/
│   │   ├── conversation_agent.py
│   │   ├── reflection_agent.py
│   │   ├── personality_agent.py
│   │   └── tool_agent.py
│   ├── memory/
│   │   ├── mem0_wrapper.py
│   │   └── schemas.sql
│   ├── tools/
│   │   ├── web_search.py
│   │   ├── code_executor.py
│   │   └── file_operations.py
│   ├── telegram/
│   │   ├── bot.py
│   │   └── handlers.py
│   └── utils/
│       ├── llm_factory.py
│       └── security.py
├── sandbox/
│   ├── Dockerfile
│   └── setup.sh
├── dashboard/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── pages/
│       ├── 1_Overview.py
│       ├── 2_Conversations.py
│       ├── 3_Memories.py
│       ├── 4_Personality.py
│       └── 5_Agents.py
├── config/
│   ├── agents.yaml
│   ├── personality.yaml
│   ├── memory.yaml
│   └── security.yaml
├── init-scripts/
│   └── init-db.sql
├── tests/
│   ├── test_agents.py
│   ├── test_memory.py
│   └── test_tools.py
└── docs/
    ├── setup-guide.md
    ├── troubleshooting.md
    └── api-reference.md
```

---

## 🎯 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Response Time** | < 2 seconds | 95th percentile |
| **Memory Search** | < 500ms | Average query time |
| **Reflection Cycle** | < 10 seconds | Per conversation window |
| **Database Writes** | < 100ms | 95th percentile |
| **Concurrent Users** | 100+ | Simultaneous conversations |
| **Uptime** | 99.5% | Monthly availability |
| **Memory Recall Accuracy** | > 90% | Semantic search relevance |

---

**Last Updated**: 2025-02-07  
**Version**: 1.0  
**Architecture Review**: Quarterly