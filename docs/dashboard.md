# HER Admin Dashboard

The HER Admin Dashboard is a comprehensive Streamlit application that provides real-time monitoring, logging, and management capabilities for the HER AI Assistant system.

## Features

### 📊 Overview Dashboard
- **Key Metrics**: Total messages, tokens, users, memories at a glance
- **Recent Activity**: Latest user interactions and events
- **Memory Categories**: Visual breakdown of memory types
- **System Status**: Service connectivity and environment info

### 📋 Logs Page
- **Real-time System Logs**: View all application logs from Redis
- **Filtering**: Filter by log level (INFO, WARNING, ERROR, DEBUG)
- **Search**: Search logs by keyword
- **Auto-refresh**: Automatically update logs at configurable intervals

### 🔧 Executors Page
- **Sandbox Execution History**: View all sandbox command executions
- **Execution Details**: Command, output, errors, execution time, exit codes
- **Statistics**: Success rate, total executions, performance metrics
- **Filtering**: Filter by success/failure status

### ⏰ Jobs Page
- **Scheduled Job History**: View all scheduled task executions
- **Job Details**: Name, type, interval, execution time, results
- **Job Configuration**: View and manage scheduled tasks
- **Next Run Times**: See when jobs will execute next

### 📈 Metrics Page
- **Token Usage Over Time**: Visual chart of token consumption
- **Message Statistics**: Detailed message and user metrics
- **Recent Interactions**: Table of recent user interactions
- **Performance Metrics**: Response times and system performance

### 💾 Memory Page
- **Memory Statistics**: Total memories, users with memories
- **Category Breakdown**: Visual charts of memory categories
- **Memory Creation Trends**: Daily memory creation over last 30 days
- **Memory Search**: Search memories by keyword with full-text search

### 🏥 System Health Page
- **Service Status**: Redis and PostgreSQL connectivity
- **Service Information**: Version info, memory usage, connection status
- **Environment Info**: Configuration and environment variables
- **Health Checks**: Real-time service health monitoring

## Access

The dashboard runs on port `8501` and is accessible at:
```
http://localhost:8501
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
- `her:scheduler:jobs` - Scheduled job history (last 100)

### PostgreSQL Tables
- `memories` - Long-term memory storage
- Memory statistics and search queries

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
