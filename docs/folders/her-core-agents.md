# Code Area: her-core/agents

## Purpose

Defines CrewAI agent roles and orchestration wiring.

## Files

- `her-core/agents/base_agent.py` - shared config load + LLM wiring
- `her-core/agents/conversation_agent.py` - user-facing conversational behavior
- `her-core/agents/reflection_agent.py` - memory curation behavior
- `her-core/agents/personality_agent.py` - personality trait management
- `her-core/agents/tool_agent.py` - tool execution role
- `her-core/agents/crew_orchestrator.py` - task definitions + crew composition

## How to Test

```bash
pytest tests/test_smoke.py -q
pytest tests/test_runtime_guards.py -q
```
