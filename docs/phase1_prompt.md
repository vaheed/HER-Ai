# HER Phase 1 - Foundation Build Prompt

> Copy this prompt to Claude/ChatGPT to generate the complete Phase 1 project structure

---

## 🎯 Objective
Build Phase 1 (Weeks 1-3) of the HER AI Assistant: complete Docker infrastructure, memory system (Mem0 + PostgreSQL + Redis), and CrewAI agent architecture. Make it 100% functional and ready for Telegram integration.

## 📦 Project Structure Required

```
her-ai-assistant/
├── docker-compose.yml
├── .env.example
├── README.md
├── her-core/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── mem0_client.py
│   │   ├── redis_client.py
│   │   └── schemas.sql
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── conversation_agent.py
│   │   ├── reflection_agent.py
│   │   ├── personality_agent.py
│   │   └── base_agent.py
│   └── utils/
│       ├── __init__.py
│       └── llm_factory.py
├── config/
│   ├── agents.yaml
│   ├── personality.yaml
│   └── memory.yaml
└── init-scripts/
    └── init-db.sql
```

## 🔧 Technical Requirements

### 1. Docker Compose Setup
Create `docker-compose.yml` with:
- **her-bot**: Python 3.11-slim, expose port 8000 for health checks
- **postgres**: pgvector/pgvector:pg16, persistent volume
- **redis**: redis:7-alpine with password auth, AOF persistence
- **her-network**: bridge network for all services
- Health checks for all containers
- Auto-restart policies

### 2. PostgreSQL Database
Initialize with `init-scripts/init-db.sql`:
```sql
-- Install pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Tables needed:
-- 1. users (user_id, username, mode, created_at, last_interaction, preferences JSONB)
-- 2. memories (memory_id UUID, user_id, memory_text, embedding vector(1536), category, importance_score, created_at, metadata JSONB)
-- 3. personality_states (state_id, user_id, warmth, curiosity, assertiveness, humor, emotional_depth, version, created_at, changes JSONB)
-- 4. conversation_logs (log_id UUID, user_id, role, message, timestamp, metadata JSONB)

-- Create indexes:
-- - Vector similarity index on memories.embedding (ivfflat)
-- - B-tree indexes on user_id, created_at, importance_score
```

### 3. Memory System (Mem0)
**File: `her-core/memory/mem0_client.py`**

Implement `HERMemory` class:
- Initialize Mem0 with pgvector backend (PostgreSQL)
- Redis cache layer with 24h TTL
- Methods:
  - `add_memory(user_id, text, category, importance)` → stores with embedding
  - `search_memories(user_id, query, limit=5)` → semantic search
  - `get_context(user_id)` → fetch from Redis
  - `update_context(user_id, message, role)` → store last 20 messages in Redis
- Use `text-embedding-3-small` model for embeddings

**File: `her-core/memory/redis_client.py`**
- Simple Redis wrapper for context storage
- JSON serialization/deserialization
- TTL management (86400 seconds)

### 4. CrewAI Agents
**File: `her-core/agents/base_agent.py`**
- Base agent class with common LLM initialization
- Load config from YAML files
- Error handling wrapper

**File: `her-core/agents/conversation_agent.py`**
```python
from crewai import Agent
# Role: "Empathetic Conversationalist"
# Goal: "Engage users warmly while remembering context"
# Tools: [memory_search] (for now)
# LLM: OpenAI GPT-4-turbo or Groq llama3-70b (from env)
```

**File: `her-core/agents/reflection_agent.py`**
```python
from crewai import Agent
# Role: "Memory Curator"  
# Goal: "Analyze conversations and store important memories"
# No tools needed yet
# LLM: GPT-4-turbo or Groq mixtral
# Method: analyze_conversation(messages) → returns memories to store
```

**File: `her-core/agents/personality_agent.py`**
```python
from crewai import Agent
# Role: "Personality Manager"
# Goal: "Track and evolve personality traits safely"
# Stores: {warmth: 75, curiosity: 80, assertiveness: 60, humor: 70, emotional_depth: 85}
# Methods: 
#   - get_current_traits(user_id)
#   - adjust_trait(user_id, trait_name, delta) with bounds [20, 95]
#   - save_version(user_id, traits, notes)
```

### 5. LLM Factory
**File: `her-core/utils/llm_factory.py`**
```python
# Support OpenAI and Groq providers
# Read from environment: LLM_PROVIDER, OPENAI_API_KEY, GROQ_API_KEY
# Return configured LLM object for CrewAI
# Default: OpenAI gpt-4-turbo-preview
```

### 6. Main Application
**File: `her-core/main.py`**
```python
# Initialize all components:
# 1. Load environment variables
# 2. Initialize HERMemory
# 3. Create agents (conversation, reflection, personality)
# 4. Simple test: simulate a conversation, store memory, retrieve it
# 5. Print success message with all components status

# For now: just validate everything works, no Telegram yet
```

### 7. Configuration Files
**File: `config/agents.yaml`**
```yaml
conversation_agent:
  role: "Empathetic Conversationalist"
  goal: "Engage users with warmth and context"
  temperature: 0.7
  max_tokens: 500

reflection_agent:
  role: "Memory Curator"
  goal: "Preserve meaningful moments"
  temperature: 0.3
  importance_threshold: 0.7
  
personality_agent:
  role: "Personality Manager"
  evolution_speed: "medium"
  boundaries: {min: 20, max: 95}
```

**File: `config/personality.yaml`**
```yaml
default_traits:
  warmth: 75
  curiosity: 80
  assertiveness: 60
  humor: 70
  emotional_depth: 85

immutable_values:
  - empathy
  - safety_awareness
```

**File: `config/memory.yaml`**
```yaml
short_term:
  ttl: 86400  # 24 hours
  max_messages: 20

long_term:
  importance_threshold: 0.7
  embedding_model: "text-embedding-3-small"
  vector_dimensions: 1536
```

### 8. Environment Variables
**File: `.env.example`**
```bash
# LLM Provider (openai or groq)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# Database
POSTGRES_USER=her
POSTGRES_PASSWORD=changeme123
POSTGRES_DB=her_memory
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis  
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=changeme456

# App
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### 9. Dockerfile
**File: `her-core/Dockerfile`**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "main.py"]
```

### 10. Requirements
**File: `her-core/requirements.txt`**
```
crewai==0.28.0
mem0ai==0.0.9
openai==1.12.0
groq==0.4.2
psycopg2-binary==2.9.9
redis==5.0.1
pyyaml==6.0.1
python-dotenv==1.0.0
pydantic==2.6.0
```

## ✅ Success Criteria (Phase 1 Complete)

When you run:
```bash
docker-compose up -d
docker-compose logs -f her-bot
```

You should see:
```
✓ PostgreSQL connected with pgvector enabled
✓ Redis connected
✓ Mem0 initialized
✓ Conversation Agent created
✓ Reflection Agent created  
✓ Personality Agent created
✓ Test: Stored memory with embedding
✓ Test: Retrieved memory via semantic search
✓ Test: Personality trait updated
🎉 HER Phase 1 Complete - All systems operational!
```

## 🎯 Deliverables Checklist
- [ ] All files created with proper structure
- [ ] Docker containers start successfully
- [ ] PostgreSQL has all tables with pgvector
- [ ] Redis stores/retrieves context
- [ ] Mem0 stores/searches memories with embeddings
- [ ] All 3 CrewAI agents initialize
- [ ] Test conversation creates memories
- [ ] Semantic search returns relevant memories
- [ ] Personality traits save to database
- [ ] No errors in logs

---

**Build this Phase 1 foundation. Make it solid, tested, and ready for Phase 2 (Telegram Bot).**