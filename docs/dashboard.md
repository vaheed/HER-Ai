# HER Admin Dashboard

The HER Admin Dashboard is a comprehensive Streamlit application that provides real-time monitoring, logging, and management capabilities for the HER AI Assistant system.

Charts use Plotly for responsive, interactive visuals (zoom, pan, hover, legend toggles).

## Features

### 📊 Overview Dashboard
- **Key Metrics**: Total messages, tokens, users, memories at a glance
- **Capability Diagnostics**: Internet/sandbox/MCP status with reasons, server table, and startup history trend
- **MCP Failure Report**: Error counts by server and top recurring failure messages
- **Traffic & Log Trends**: Messages/tokens over time and log-level distribution charts
- **Memory Summary**: Side-by-side short-memory (Redis) and long-memory (PostgreSQL) health cards
- **System Status**: Service connectivity and environment info

### 📋 Logs Page
- **Real-time System Logs**: View all application logs from Redis
- **Filtering**: Filter by log level (INFO, WARNING, ERROR, DEBUG)
- **Search**: Search logs by keyword
- **MCP Error Analytics**: Dedicated diagnostics for MCP startup/JSON-RPC failures
- **Auto-refresh**: Automatically update logs at configurable intervals

### 💬 Recent Chats Page
- **Recent Interaction Events**: User messages + assistant responses from `her:metrics:events`
- **Redis Context Threads**: Latest context snippets from `her:context:*`
- **Quick Debugging**: Validate whether chat history is being persisted
- **Redis Type Safe**: Context reads support both string-backed JSON threads and list-backed legacy keys without `WRONGTYPE` errors

### 🔧 Executors Page
- **Sandbox Execution History**: View all sandbox command executions
- **Execution Details**: Command, output, errors, execution time, exit codes
- **Statistics**: Success rate, total executions, performance metrics
- **Filtering**: Filter by success/failure status

### ⏰ Jobs Page
- **Scheduled Job History**: View all scheduled task executions
- **Upcoming Jobs**: Live upcoming schedule from `her:scheduler:state`
- **Autonomy Snapshot**: Engagement score, initiative level, mood, and daily proactive target
- **Debate Trace**: Planner/Skeptic/Verifier decision stream for action requests
- **Daily Reflection Feed**: Reflection events with initiative adjustments and notes
- **Job Details**: Name, type, interval, execution time, results
- **Job Configuration**: View and manage scheduled tasks
- **Next Run Times**: See when jobs will execute next

### 🧾 Decisions Page
- **Decision Audit Trail**: View runtime decisions and actions from Redis key `her:decision:logs`
- **Transparency Metrics**: Breakdown of decision event types (scheduler, capability probes, reply generation)
- **Autonomy Trend**: Engagement and initiative trend lines over time
- **Debugging Support**: Correlate decisions with logs and job outcomes
- **Reinforcement Traceability**: Reinforcement scoring decisions appear as `reinforcement_event` entries

### 📈 Metrics Page
- **Token Usage Over Time**: Visual chart of token consumption
- **Message Statistics**: Detailed message and user metrics
- **Recent Interactions**: Table of recent user interactions
- **Performance Metrics**: Response times and system performance

### 💾 Memory Page
- **Short Memory Report**: Redis context thread totals, role distribution, largest threads
- **Long Memory Report**: Totals, 24h growth, average importance, top users
- **Category Breakdown**: Visual charts of long-memory categories
- **Memory Creation Trends**: Daily long-memory creation over last 30 days
- **Recent Long-Memory Feed**: Latest persisted memory rows
- **Memory Search**: Search memories by keyword with full-text search
- **Schema Compatibility**: Supports both legacy memory schema and Mem0 payload schema

### 🏥 System Health Page
- **Service Status**: Redis and PostgreSQL connectivity
- **Service Information**: Version info, memory usage, connection status
- **Environment Info**: Configuration and environment variables
- **Health Checks**: Real-time service health monitoring
- **Runtime Snapshot**: Raw startup capability payload from `her:runtime:capabilities`

### 🧠 Workflow Debugger (Realtime DAG)
- **WebSocket Event Stream**: `ws://localhost:8081/ws/workflow`
- **Execution Graph**: Input → Intent Classifier → Memory Lookup → Tool Selector → Tool Executor/LLM → Response
- **Timeline + Latency**: Node durations and total request latency
- **Live Console**: Streaming tool stdout/stderr and stage transitions
- **Debug Toggle**: `http://localhost:8081/workflow?debug=true` reveals raw LLM prompts + tool I/O

## Access

The dashboard runs on port `8501` and is accessible at:
```
http://localhost:8501
```

Realtime workflow debugger:
```
http://localhost:8081/workflow
```

## Configuration

The dashboard automatically connects to:
- **Redis**: For metrics, logs, and execution history
- **PostgreSQL**: For memory statistics and search

Configure these in your `.env` file:
```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_password

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=her
POSTGRES_PASSWORD=your_password
POSTGRES_DB=her_memory
TZ=UTC
USER_TIMEZONE=UTC
```

## Data Sources

### Redis Keys
- `her:metrics:tokens` - Total token count
- `her:metrics:messages` - Total message count
- `her:metrics:users` - Set of unique user IDs
- `her:metrics:events` - List of recent interactions (last 50)
- `her:metrics:last_response` - Most recent response data
- `her:logs` - System logs (last 200)
- `her:sandbox:executions` - Sandbox execution history (last 100)
- `her:decision:logs` with `event_type=sandbox_execution` - Fallback sandbox execution feed when direct list entries are unavailable
- `her:scheduler:jobs` - Scheduled job history (last 100)
- `her:scheduler:state` - Scheduler runtime state and upcoming jobs
- `her:scheduler:state` field `autonomy` - Current user-level autonomy/mood snapshot
- `her:decision:logs` with `event_type=reminder_state_change` - Reminder lifecycle transitions
- `her:decision:logs` with `event_type=timezone_conversion` - Reminder local-time to UTC conversion audit
- `her:decision:logs` with `event_type=internal_debate`/`verifier_result` - internal cognitive debate visibility
- `her:decision:logs` with `event_type=reflection` - daily self-reflection events
- `her:decision:logs` - Runtime decision log feed (last 500)
- `her:reinforcement:events` - Reinforcement score/event history (last 1000)
- `her:runtime:capabilities` - Latest startup capability snapshot (internet/sandbox/MCP)
- `her:runtime:capabilities:history` - Capability snapshot history (last 100)

### PostgreSQL Tables
- `memories` - Long-term memory storage
- Memory statistics and search queries
- `conversation_logs` - Optional conversation timeline (if enabled by runtime)

## Auto-Refresh

The dashboard supports auto-refresh:
- Enable/disable in sidebar
- Configurable refresh interval (1-60 seconds)
- Manual refresh button available

## Usage Tips

1. **Monitor Logs**: Use the Logs page to debug issues and monitor system activity
2. **Track Executions**: Check Executors page to see what commands are running in sandbox
3. **Job Management**: Use Jobs page to monitor scheduled tasks and their execution history
4. **Memory Insights**: Use Memory page to understand what HER is remembering
5. **Health Monitoring**: Check System Health page regularly to ensure all services are running

## Troubleshooting

### Dashboard not loading
- Check that Redis and PostgreSQL are running
- Verify environment variables are set correctly
- Check dashboard logs: `docker compose logs dashboard`

### No data showing
- Ensure HER bot is running and generating metrics
- Check Redis connectivity
- Verify PostgreSQL connection

### Logs not appearing
- Ensure Redis log handler is enabled in main.py
- Check Redis key `her:logs` exists
- Verify log level is set appropriately

## Related Documentation

- [Architecture Overview](architecture.md)
- [MCP Integration Guide](mcp_guide.md)
- [Testing Playbook](testing_playbook.md)
