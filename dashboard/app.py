"""Enhanced HER Admin Dashboard with comprehensive monitoring.

Features:
- Real-time logs
- Sandbox executor history
- Scheduled jobs status
- Detailed metrics
- Memory statistics
- Agent activity
- System health
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2
import redis
import streamlit as st

st.set_page_config(page_title="HER Admin Dashboard", layout="wide", initial_sidebar_state="expanded")

# Initialize session state
if "refresh_interval" not in st.session_state:
    st.session_state.refresh_interval = 5

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "her")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "her_memory")


@st.cache_resource
def get_redis_client():
    """Get Redis client."""
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )
    except Exception as exc:
        st.error(f"Failed to connect to Redis: {exc}")
        return None


@st.cache_resource
def get_postgres_connection():
    """Get PostgreSQL connection."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB,
        )
        # Avoid "current transaction is aborted" after a failed query.
        conn.autocommit = True
        return conn
    except Exception as exc:
        st.error(f"Failed to connect to PostgreSQL: {exc}")
        return None


def get_metrics(redis_client):
    """Get metrics from Redis."""
    if not redis_client:
        return {}
    try:
        return {
            "total_tokens": int(redis_client.get("her:metrics:tokens") or 0),
            "total_messages": int(redis_client.get("her:metrics:messages") or 0),
            "unique_users": int(redis_client.scard("her:metrics:users") or 0),
            "last_response": redis_client.get("her:metrics:last_response"),
            "events": redis_client.lrange("her:metrics:events", 0, 99),
            "logs": redis_client.lrange("her:logs", 0, 199),  # Recent logs
            "sandbox_executions": redis_client.lrange("her:sandbox:executions", 0, 99),
            "scheduled_jobs": redis_client.lrange("her:scheduler:jobs", 0, 99),
        }
    except Exception as exc:
        st.warning(f"Error fetching metrics: {exc}")
        return {}


def get_memory_stats(pg_conn):
    """Get memory statistics from PostgreSQL."""
    if not pg_conn:
        return {}
    try:
        cursor = pg_conn.cursor()
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'memories'
            """
        )
        memory_columns = {row[0] for row in cursor.fetchall()}
        if not memory_columns:
            cursor.close()
            return {}

        cursor.execute("SELECT COUNT(*) FROM memories")
        total_memories = cursor.fetchone()[0]

        if "user_id" in memory_columns:
            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM memories")
            users_with_memories = cursor.fetchone()[0]
        elif "payload" in memory_columns:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT payload->>'user_id')
                FROM memories
                WHERE payload->>'user_id' IS NOT NULL
                """
            )
            users_with_memories = cursor.fetchone()[0]
        else:
            users_with_memories = 0

        if "category" in memory_columns:
            cursor.execute(
                """
                SELECT COALESCE(category, 'uncategorized') AS category, COUNT(*) AS count
                FROM memories
                GROUP BY COALESCE(category, 'uncategorized')
                ORDER BY count DESC
                LIMIT 10
                """
            )
            category_counts = {row[0]: row[1] for row in cursor.fetchall()}
        elif "payload" in memory_columns:
            cursor.execute(
                """
                SELECT COALESCE(payload->'metadata'->>'category', 'uncategorized') AS category, COUNT(*) AS count
                FROM memories
                GROUP BY COALESCE(payload->'metadata'->>'category', 'uncategorized')
                ORDER BY count DESC
                LIMIT 10
                """
            )
            category_counts = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            category_counts = {}

        if "created_at" in memory_columns:
            cursor.execute(
                """
                SELECT DATE(created_at) AS date, COUNT(*) AS count
                FROM memories
                WHERE created_at > NOW() - INTERVAL '30 days'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                """
            )
            daily_memories = {str(row[0]): row[1] for row in cursor.fetchall()}
        else:
            daily_memories = {}

        cursor.close()
        return {
            "total_memories": total_memories,
            "users_with_memories": users_with_memories,
            "category_counts": category_counts,
            "daily_memories": daily_memories,
        }
    except Exception as exc:
        try:
            pg_conn.rollback()
        except Exception:
            pass
        st.warning(f"Error fetching memory stats: {exc}")
        return {}


def get_recent_chats(redis_client, limit: int = 100) -> list[dict[str, Any]]:
    """Get recent chat snippets from Redis context keys."""
    if not redis_client:
        return []
    try:
        chats: list[dict[str, Any]] = []
        for key in redis_client.scan_iter(match="her:context:*", count=200):
            entries = redis_client.lrange(key, 0, 5)
            if not entries:
                continue
            last_message = ""
            last_role = ""
            for raw in entries:
                try:
                    item = json.loads(raw)
                except Exception:
                    continue
                if isinstance(item, dict):
                    last_role = str(item.get("role", "unknown"))
                    last_message = str(item.get("message", ""))
                    if last_message:
                        break
            chats.append(
                {
                    "context_key": key,
                    "last_role": last_role or "unknown",
                    "last_message": (last_message or "")[:200],
                    "message_count": redis_client.llen(key),
                }
            )
            if len(chats) >= limit:
                break
        chats.sort(key=lambda c: c["message_count"], reverse=True)
        return chats
    except Exception as exc:
        st.warning(f"Error fetching recent chats: {exc}")
        return []


def get_runtime_capabilities(redis_client) -> dict[str, Any]:
    """Get runtime capability status snapshot from Redis."""
    if not redis_client:
        return {}
    try:
        raw = redis_client.get("her:runtime:capabilities")
        if not raw:
            return {}
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
        return {}
    except Exception as exc:
        st.warning(f"Error fetching runtime capabilities: {exc}")
        return {}


def format_log_entry(entry: str) -> dict[str, Any]:
    """Parse log entry."""
    try:
        return json.loads(entry)
    except (json.JSONDecodeError, TypeError):
        return {"raw": entry, "timestamp": datetime.now(timezone.utc).isoformat()}


# Sidebar
with st.sidebar:
    st.title("HER Dashboard")
    st.markdown("---")

    # Auto-refresh
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    if auto_refresh:
        refresh_interval = st.slider("Refresh interval (seconds)", 1, 60, 5)
        st.session_state.refresh_interval = refresh_interval

    st.markdown("---")
    st.markdown("### Navigation")
    page = st.radio(
        "Select Page",
        [
            "Overview",
            "Recent Chats",
            "Logs",
            "Executors",
            "Jobs",
            "Metrics",
            "Memory",
            "System Health",
        ],
    )

    st.markdown("---")
    st.markdown("### Quick Actions")
    if st.button("🔄 Refresh Now"):
        st.cache_resource.clear()
        st.rerun()

# Main content
redis_client = get_redis_client()
pg_conn = get_postgres_connection()
metrics = get_metrics(redis_client)
memory_stats = get_memory_stats(pg_conn)
recent_chats = get_recent_chats(redis_client, limit=50)
runtime_capabilities = get_runtime_capabilities(redis_client)

if page == "Overview":
    st.title("📊 Overview Dashboard")

    # Key Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Messages", metrics.get("total_messages", 0))
    with col2:
        st.metric("Total Tokens", f"{metrics.get('total_tokens', 0):,}")
    with col3:
        st.metric("Unique Users", metrics.get("unique_users", 0))
    with col4:
        st.metric("Total Memories", memory_stats.get("total_memories", 0))

    st.markdown("---")

    # Recent Activity
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📝 Recent Events")
        events = metrics.get("events", [])
        if events:
            for event_str in events[:10]:
                try:
                    event = json.loads(event_str)
                    timestamp = event.get("timestamp", "")
                    user_id = event.get("user_id", "unknown")
                    st.text(f"[{timestamp[:19]}] User {user_id}: {event.get('user_message', '')[:50]}...")
                except Exception:
                    st.text(event_str[:100])
        else:
            st.info("No recent events")

    with col2:
        st.subheader("💾 Memory Categories")
        categories = memory_stats.get("category_counts", {})
        if categories:
            st.bar_chart(categories)
        else:
            st.info("No memory categories yet")

    st.markdown("---")

    # System Status
    st.subheader("🔧 System Status")
    status_col1, status_col2, status_col3 = st.columns(3)

    with status_col1:
        st.write("**Services**")
        st.write("✅ Redis: Connected" if redis_client else "❌ Redis: Disconnected")
        st.write("✅ PostgreSQL: Connected" if pg_conn else "❌ PostgreSQL: Disconnected")

    with status_col2:
        st.write("**Environment**")
        st.write(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
        st.write(f"LLM Provider: {os.getenv('LLM_PROVIDER', 'ollama')}")

    with status_col3:
        st.write("**Last Updated**")
        st.write(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))

    st.markdown("---")
    st.subheader("🧭 Capability Status")
    capabilities = runtime_capabilities.get("capabilities", {})
    mcp_servers = runtime_capabilities.get("mcp_servers", {})

    cap_col1, cap_col2, cap_col3 = st.columns(3)
    internet = capabilities.get("internet", {})
    sandbox = capabilities.get("sandbox", {})
    mcp_running = sum(1 for item in mcp_servers.values() if item.get("status") == "running")
    mcp_total = len(mcp_servers)

    with cap_col1:
        if internet.get("available") is True:
            st.success("Internet: Available")
        elif internet:
            st.warning("Internet: Degraded")
        else:
            st.info("Internet: Unknown")
        if internet.get("reason"):
            st.caption(str(internet.get("reason")))

    with cap_col2:
        if sandbox.get("available") is True:
            st.success("Sandbox: Available")
        elif sandbox:
            st.warning("Sandbox: Degraded")
        else:
            st.info("Sandbox: Unknown")
        if sandbox.get("reason"):
            st.caption(str(sandbox.get("reason")))

    with cap_col3:
        if mcp_total == 0:
            st.info("MCP: Not reported")
        elif mcp_running == mcp_total:
            st.success(f"MCP: {mcp_running}/{mcp_total} running")
        else:
            st.warning(f"MCP: {mcp_running}/{mcp_total} running")

    if mcp_servers:
        with st.expander("MCP server details"):
            for server_name, server_state in mcp_servers.items():
                server_status = str(server_state.get("status", "unknown"))
                server_msg = str(server_state.get("message", ""))
                st.write(f"- `{server_name}`: **{server_status}** - {server_msg}")
    else:
        st.info("No runtime capability snapshot published yet.")

elif page == "Logs":
    st.title("📋 System Logs")

    log_level = st.selectbox("Filter by Level", ["All", "INFO", "WARNING", "ERROR", "DEBUG"])
    search_term = st.text_input("Search logs", "")

    logs = metrics.get("logs", [])
    if not logs:
        # Try to get logs from Redis
        if redis_client:
            logs = redis_client.lrange("her:logs", 0, 199)

    if logs:
        st.subheader(f"Recent Logs ({len(logs)} entries)")

        filtered_logs = []
        for log_entry in logs:
            entry = format_log_entry(log_entry)
            level = entry.get("level", "").upper()
            message = entry.get("message", entry.get("raw", str(log_entry)))

            if log_level != "All" and level != log_level:
                continue
            if search_term and search_term.lower() not in str(message).lower():
                continue

            filtered_logs.append(entry)

        # Display logs in reverse order (newest first)
        for entry in reversed(filtered_logs[-100:]):
            level = entry.get("level", "INFO").upper()
            timestamp = entry.get("timestamp", entry.get("raw", ""))[:19]
            message = entry.get("message", entry.get("raw", str(entry)))

            if level == "ERROR":
                st.error(f"[{timestamp}] {message}")
            elif level == "WARNING":
                st.warning(f"[{timestamp}] {message}")
            elif level == "DEBUG":
                st.text(f"[{timestamp}] DEBUG: {message}")
            else:
                st.text(f"[{timestamp}] {message}")

        st.info(f"Showing {len(filtered_logs)} of {len(logs)} log entries")
    else:
        st.info("No logs available. Logs are stored in Redis under 'her:logs' key.")

elif page == "Recent Chats":
    st.title("💬 Recent Chats")

    events = metrics.get("events", [])
    if events:
        st.subheader("Recent Interaction Events")
        for event_str in events[:50]:
            try:
                event = json.loads(event_str)
                timestamp = str(event.get("timestamp", ""))[:19]
                user_id = event.get("user_id", "unknown")
                user_msg = str(event.get("user_message", "")).strip()
                response_msg = str(event.get("response_message", "")).strip()
                with st.expander(f"[{timestamp}] User {user_id}"):
                    st.write(f"**User:** {user_msg or '(empty)'}")
                    st.write(f"**Assistant:** {response_msg or '(empty)'}")
                    st.write(f"**Tokens:** {event.get('token_estimate', 0)}")
            except Exception:
                st.text(str(event_str)[:300])
    else:
        st.info("No interaction events found yet.")

    st.markdown("---")
    st.subheader("Redis Context Threads")
    if recent_chats:
        for item in recent_chats[:50]:
            with st.expander(f"{item['context_key']} ({item['message_count']} msgs)"):
                st.write(f"**Last role:** {item['last_role']}")
                st.write(f"**Last message:** {item['last_message'] or '(empty)'}")
    else:
        st.info("No Redis context threads found yet.")

elif page == "Executors":
    st.title("🔧 Sandbox Executors")

    st.subheader("Recent Executions")
    executions = metrics.get("sandbox_executions", [])

    if executions:
        for exec_str in executions[:50]:
            try:
                exec_data = json.loads(exec_str)
                with st.expander(
                    f"Execution: {exec_data.get('command', 'unknown')[:50]} - {exec_data.get('timestamp', '')[:19]}"
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Command:** `{exec_data.get('command', 'N/A')}`")
                        st.write(f"**Status:** {'✅ Success' if exec_data.get('success') else '❌ Failed'}")
                        st.write(f"**Exit Code:** {exec_data.get('exit_code', 'N/A')}")
                    with col2:
                        st.write(f"**Execution Time:** {exec_data.get('execution_time', 0):.2f}s")
                        st.write(f"**User:** {exec_data.get('user', 'sandbox')}")
                        st.write(f"**Workdir:** {exec_data.get('workdir', '/workspace')}")

                    if exec_data.get("output"):
                        st.text_area("Output", exec_data.get("output"), height=100, key=f"output_{exec_data.get('timestamp')}")

                    if exec_data.get("error"):
                        st.text_area("Error", exec_data.get("error"), height=50, key=f"error_{exec_data.get('timestamp')}")
            except Exception as exc:
                st.text(f"Error parsing execution: {exc}\n{exec_str}")

        st.info(f"Showing {len(executions)} recent executions")
    else:
        st.info("No sandbox executions recorded yet. Executions are logged to Redis under 'her:sandbox:executions'.")

    # Executor Statistics
    if executions:
        st.markdown("---")
        st.subheader("Executor Statistics")
        success_count = sum(1 for e in executions if json.loads(e).get("success", False))
        total_count = len(executions)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Executions", total_count)
        col2.metric("Successful", success_count)
        col3.metric("Success Rate", f"{success_rate:.1f}%")

elif page == "Jobs":
    st.title("⏰ Scheduled Jobs")

    jobs = metrics.get("scheduled_jobs", [])

    if jobs:
        st.subheader("Job History")
        for job_str in jobs[:50]:
            try:
                job_data = json.loads(job_str)
                status_icon = "✅" if job_data.get("success") else "❌"
                with st.expander(
                    f"{status_icon} {job_data.get('name', 'Unknown')} - {job_data.get('timestamp', '')[:19]}"
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Name:** {job_data.get('name', 'N/A')}")
                        st.write(f"**Type:** {job_data.get('type', 'N/A')}")
                        st.write(f"**Interval:** {job_data.get('interval', 'N/A')}")
                    with col2:
                        st.write(f"**Status:** {'Success' if job_data.get('success') else 'Failed'}")
                        st.write(f"**Execution Time:** {job_data.get('execution_time', 0):.2f}s")
                        st.write(f"**Next Run:** {job_data.get('next_run', 'N/A')}")

                    if job_data.get("result"):
                        st.text_area("Result", job_data.get("result"), height=100, key=f"result_{job_data.get('timestamp')}")

                    if job_data.get("error"):
                        st.error(f"Error: {job_data.get('error')}")
            except Exception as exc:
                st.text(f"Error parsing job: {exc}\n{job_str}")

        st.info(f"Showing {len(jobs)} recent job executions")
    else:
        st.info("No scheduled jobs executed yet. Jobs are logged to Redis under 'her:scheduler:jobs'.")

    # Job Statistics
    st.markdown("---")
    st.subheader("Job Configuration")
    st.info("Configure scheduled jobs in config/scheduler.yaml")

elif page == "Metrics":
    st.title("📈 Detailed Metrics")

    # Token Usage Over Time
    st.subheader("Token Usage")
    events = metrics.get("events", [])
    if events:
        token_data = []
        for event_str in events[-100:]:
            try:
                event = json.loads(event_str)
                token_data.append(
                    {
                        "timestamp": event.get("timestamp", "")[:19],
                        "tokens": event.get("token_estimate", 0),
                    }
                )
            except Exception:
                pass

        if token_data:
            import pandas as pd

            df = pd.DataFrame(token_data)
            st.line_chart(df.set_index("timestamp")["tokens"])

    # Message Statistics
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Messages", metrics.get("total_messages", 0))
    with col2:
        st.metric("Total Tokens", f"{metrics.get('total_tokens', 0):,}")
    with col3:
        st.metric("Unique Users", metrics.get("unique_users", 0))

    # Recent Interactions
    st.markdown("---")
    st.subheader("Recent Interactions")
    events = metrics.get("events", [])
    if events:
        import pandas as pd

        interaction_data = []
        for event_str in events[:20]:
            try:
                event = json.loads(event_str)
                interaction_data.append(
                    {
                        "Timestamp": event.get("timestamp", "")[:19],
                        "User": event.get("user_id", "unknown"),
                        "Message": event.get("user_message", "")[:50] + "...",
                        "Tokens": event.get("token_estimate", 0),
                    }
                )
            except Exception:
                pass

        if interaction_data:
            df = pd.DataFrame(interaction_data)
            st.dataframe(df, use_container_width=True)

elif page == "Memory":
    st.title("💾 Memory Statistics")

    mem_stats = memory_stats
    if mem_stats:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Overview")
            st.metric("Total Memories", mem_stats.get("total_memories", 0))
            st.metric("Users with Memories", mem_stats.get("users_with_memories", 0))

        with col2:
            st.subheader("Memory Categories")
            categories = mem_stats.get("category_counts", {})
            if categories:
                st.bar_chart(categories)
            else:
                st.info("No memory categories yet")

        # Daily Memory Creation
        st.markdown("---")
        st.subheader("Memory Creation (Last 30 Days)")
        daily = mem_stats.get("daily_memories", {})
        if daily:
            import pandas as pd

            df = pd.DataFrame(list(daily.items()), columns=["Date", "Count"])
            st.line_chart(df.set_index("Date"))

        # Memory Search
        st.markdown("---")
        st.subheader("Search Memories")
        search_query = st.text_input("Search query")
        if search_query and pg_conn:
            try:
                cursor = pg_conn.cursor()
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'memories'
                    """
                )
                memory_columns = {row[0] for row in cursor.fetchall()}

                if "memory_text" in memory_columns:
                    cursor.execute(
                        """
                        SELECT memory_text, category, created_at, importance_score
                        FROM memories
                        WHERE memory_text ILIKE %s
                        ORDER BY created_at DESC
                        LIMIT 20
                        """,
                        (f"%{search_query}%",),
                    )
                elif "payload" in memory_columns:
                    cursor.execute(
                        """
                        SELECT
                            COALESCE(payload->>'memory', payload->>'text', payload::text) AS memory_text,
                            COALESCE(payload->'metadata'->>'category', 'uncategorized') AS category,
                            created_at,
                            COALESCE((payload->'metadata'->>'importance')::float, 0) AS importance_score
                        FROM memories
                        WHERE payload::text ILIKE %s
                        ORDER BY created_at DESC NULLS LAST
                        LIMIT 20
                        """,
                        (f"%{search_query}%",),
                    )
                else:
                    st.info("Memories table is present but not in a searchable schema.")
                    cursor.close()
                    results = []

                if "memory_text" in memory_columns or "payload" in memory_columns:
                    results = cursor.fetchall()
                    cursor.close()

                if results:
                    for row in results:
                        with st.expander(f"{row[1]} - {row[2]}"):
                            st.write(f"**Text:** {row[0]}")
                            st.write(f"**Importance:** {row[3]}")
                else:
                    st.info("No memories found")
            except Exception as exc:
                try:
                    pg_conn.rollback()
                except Exception:
                    pass
                st.error(f"Search error: {exc}")
    else:
        st.info("No memory statistics available")

elif page == "System Health":
    st.title("🏥 System Health")

    # Service Status
    st.subheader("Service Status")
    col1, col2 = st.columns(2)

    with col1:
        st.write("**Redis**")
        if redis_client:
            try:
                redis_client.ping()
                st.success("✅ Connected")
                info = redis_client.info()
                st.text(f"Version: {info.get('redis_version', 'N/A')}")
                st.text(f"Used Memory: {info.get('used_memory_human', 'N/A')}")
            except Exception as exc:
                st.error(f"❌ Error: {exc}")
        else:
            st.error("❌ Not connected")

    with col2:
        st.write("**PostgreSQL**")
        if pg_conn:
            try:
                cursor = pg_conn.cursor()
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                cursor.close()
                st.success("✅ Connected")
                st.text(f"Version: {version[:50]}...")
            except Exception as exc:
                st.error(f"❌ Error: {exc}")
        else:
            st.error("❌ Not connected")

    # Environment Info
    st.markdown("---")
    st.subheader("Environment Information")
    env_col1, env_col2 = st.columns(2)

    with env_col1:
        st.write(f"**Environment:** {os.getenv('ENVIRONMENT', 'development')}")
        st.write(f"**LLM Provider:** {os.getenv('LLM_PROVIDER', 'ollama')}")
        st.write(f"**Postgres Host:** {POSTGRES_HOST}")

    with env_col2:
        st.write(f"**Redis Host:** {REDIS_HOST}")
        st.write(f"**Postgres DB:** {POSTGRES_DB}")
        st.write(f"**Last Check:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    st.markdown("---")
    st.subheader("Runtime Capability Snapshot")
    if runtime_capabilities:
        st.json(runtime_capabilities)
    else:
        st.info(
            "No capability snapshot found. The bot publishes this under "
            "`her:runtime:capabilities` after startup."
        )

# Auto-refresh
if auto_refresh:
    import time

    time.sleep(st.session_state.refresh_interval)
    st.rerun()
