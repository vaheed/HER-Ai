"""Enhanced HER Admin Dashboard with comprehensive monitoring and diagnostics."""

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import psycopg2
import redis
import streamlit as st

st.set_page_config(page_title="HER Admin Dashboard", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.0rem; padding-bottom: 1.0rem;}
      .kpi-card {
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 12px;
        padding: 0.8rem 1rem;
        background: #ffffff;
      }
      .section-note {
        color: #5f6368;
        font-size: 0.9rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

if "refresh_interval" not in st.session_state:
    st.session_state.refresh_interval = 5

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
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to connect to Redis: {exc}")
        return None


@st.cache_resource
def get_postgres_connection():
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB,
        )
        conn.autocommit = True
        return conn
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to connect to PostgreSQL: {exc}")
        return None


def parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    value = str(raw)
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


def safe_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {"raw": raw}
        except Exception:
            return {"raw": raw}
    return {"raw": str(raw)}


def _context_entries(redis_client: Any, key: str, limit: int = 20) -> list[dict[str, Any]]:
    """Read context entries from Redis key regardless of underlying Redis type."""
    if not redis_client:
        return []
    try:
        key_type = redis_client.type(key)
        if isinstance(key_type, bytes):
            key_type = key_type.decode("utf-8", errors="ignore")

        if key_type == "string":
            raw_value = redis_client.get(key)
            if not raw_value:
                return []
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return [item for item in parsed[:limit] if isinstance(item, dict)]
            return []

        if key_type == "list":
            rows = redis_client.lrange(key, 0, max(0, limit - 1))
            return [safe_json(row) for row in rows]
    except Exception:
        return []
    return []


def _context_message_count(redis_client: Any, key: str) -> int:
    """Return message count for context keys stored as string(list) or list."""
    if not redis_client:
        return 0
    try:
        key_type = redis_client.type(key)
        if isinstance(key_type, bytes):
            key_type = key_type.decode("utf-8", errors="ignore")

        if key_type == "string":
            raw_value = redis_client.get(key)
            if not raw_value:
                return 0
            parsed = json.loads(raw_value)
            return len(parsed) if isinstance(parsed, list) else 0

        if key_type == "list":
            return int(redis_client.llen(key) or 0)
    except Exception:
        return 0
    return 0


def _safe_lrange(redis_client: Any, key: str, start: int, end: int) -> list[str]:
    """Read list values while tolerating non-list Redis keys."""
    if not redis_client:
        return []
    try:
        key_type = redis_client.type(key)
        if isinstance(key_type, bytes):
            key_type = key_type.decode("utf-8", errors="ignore")
        if key_type != "list":
            return []
        return redis_client.lrange(key, start, end)
    except Exception:
        return []


def render_plotly_line(df: pd.DataFrame, x: str, y: str | list[str], title: str = "") -> None:
    if df.empty:
        st.info("No data available yet.")
        return
    fig = px.line(df, x=x, y=y, markers=True, template="plotly_white", title=title)
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=48, b=10), legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)


def render_plotly_bar(df: pd.DataFrame, x: str, y: str, title: str = "") -> None:
    if df.empty:
        st.info("No data available yet.")
        return
    fig = px.bar(df, x=x, y=y, template="plotly_white", title=title)
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=48, b=10))
    st.plotly_chart(fig, use_container_width=True)


def get_metrics(redis_client):
    if not redis_client:
        return {}
    try:
        return {
            "total_tokens": int(redis_client.get("her:metrics:tokens") or 0),
            "total_messages": int(redis_client.get("her:metrics:messages") or 0),
            "unique_users": int(redis_client.scard("her:metrics:users") or 0),
            "last_response": redis_client.get("her:metrics:last_response"),
            "events": _safe_lrange(redis_client, "her:metrics:events", 0, 199),
            "logs": _safe_lrange(redis_client, "her:logs", 0, 399),
            "sandbox_executions": _safe_lrange(redis_client, "her:sandbox:executions", 0, 199),
            "scheduled_jobs": _safe_lrange(redis_client, "her:scheduler:jobs", 0, 199),
            "decision_logs": _safe_lrange(redis_client, "her:decision:logs", 0, 499),
        }
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Error fetching metrics: {exc}")
        return {}


def get_runtime_capabilities(redis_client) -> dict[str, Any]:
    if not redis_client:
        return {}
    try:
        raw = redis_client.get("her:runtime:capabilities")
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Error fetching runtime capabilities: {exc}")
        return {}


def get_runtime_capability_history(redis_client) -> list[dict[str, Any]]:
    if not redis_client:
        return []
    try:
        rows = redis_client.lrange("her:runtime:capabilities:history", 0, 99)
        snapshots: list[dict[str, Any]] = []
        for row in rows:
            payload = safe_json(row)
            ts = parse_ts(payload.get("timestamp"))
            payload["_ts"] = ts
            snapshots.append(payload)
        snapshots.sort(key=lambda item: item.get("_ts") or datetime.min.replace(tzinfo=timezone.utc))
        return snapshots
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Error fetching capability history: {exc}")
        return []


def get_scheduler_state(redis_client) -> dict[str, Any]:
    if not redis_client:
        return {}
    try:
        raw = redis_client.get("her:scheduler:state")
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Error fetching scheduler state: {exc}")
        return {}


def get_user_timezone_stats(pg_conn) -> list[dict[str, Any]]:
    if not pg_conn:
        return []
    try:
        cursor = pg_conn.cursor()
        cursor.execute(
            """
            SELECT
                user_id,
                COALESCE(preferences->>'user_timezone', %s) AS user_timezone,
                COALESCE(preferences->>'chat_id', '') AS chat_id
            FROM users
            ORDER BY last_interaction DESC NULLS LAST
            LIMIT 200
            """,
            (os.getenv("USER_TIMEZONE", "UTC"),),
        )
        rows = [
            {"user_id": str(user_id), "user_timezone": str(user_timezone), "chat_id": str(chat_id)}
            for user_id, user_timezone, chat_id in cursor.fetchall()
        ]
        cursor.close()
        return rows
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Error fetching user timezone stats: {exc}")
        return []


def parse_reminder_events(decision_rows: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in decision_rows:
        payload = safe_json(raw)
        if str(payload.get("event_type", "")) != "reminder_state_change":
            continue
        details = payload.get("details")
        if not isinstance(details, dict):
            continue
        rows.append(
            {
                "timestamp": parse_ts(payload.get("timestamp")),
                "reminder_id": str(details.get("reminder_id", "")),
                "old_status": str(details.get("old_status", "")),
                "new_status": str(details.get("new_status", "")),
                "retry_count": int(details.get("retry_count", 0) or 0),
                "max_retries": int(details.get("max_retries", 0) or 0),
                "last_error": str(details.get("last_error", "")),
                "chat_id": str(details.get("chat_id", "")),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["timestamp"].notna()].sort_values("timestamp", ascending=False)
    return df


def parse_timezone_conversions(decision_rows: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in decision_rows:
        payload = safe_json(raw)
        details = payload.get("details")
        if not isinstance(details, dict):
            continue
        if str(details.get("event")) != "timezone_conversion":
            continue
        rows.append(
            {
                "timestamp": parse_ts(payload.get("timestamp")),
                "user_id": str(details.get("user_id", "")),
                "user_timezone": str(details.get("user_timezone", "")),
                "local_time": str(details.get("local_time", "")),
                "stored_utc": str(details.get("stored_utc", "")),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["timestamp"].notna()].sort_values("timestamp", ascending=False)
    return df


def parse_events(events: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in events:
        payload = safe_json(raw)
        ts = parse_ts(payload.get("timestamp"))
        rows.append(
            {
                "timestamp": ts,
                "user_id": str(payload.get("user_id", "unknown")),
                "token_estimate": int(payload.get("token_estimate", 0) or 0),
                "user_message": str(payload.get("user_message", "")),
                "response_message": str(payload.get("response_message", "")),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["timestamp"].notna()].sort_values("timestamp")
    return df


def parse_logs(logs: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in logs:
        payload = safe_json(raw)
        message = str(payload.get("message", payload.get("raw", "")))
        level = str(payload.get("level", "INFO")).upper()
        ts = parse_ts(payload.get("timestamp"))
        rows.append({"timestamp": ts, "level": level, "message": message})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["timestamp"].notna()].sort_values("timestamp")
    return df


def parse_execs(execs: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in execs:
        payload = safe_json(raw)
        ts = parse_ts(payload.get("timestamp"))
        rows.append(
            {
                "timestamp": ts,
                "command": str(payload.get("command", "")),
                "success": bool(payload.get("success", False)),
                "exit_code": payload.get("exit_code"),
                "execution_time": float(payload.get("execution_time", 0.0) or 0.0),
                "error": str(payload.get("error", "")),
                "output": str(payload.get("output", "")),
                "workdir": str(payload.get("workdir", "/workspace")),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["timestamp"].notna()].sort_values("timestamp")
    return df


def parse_execs_from_decisions(decision_rows: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in decision_rows:
        payload = safe_json(raw)
        if str(payload.get("event_type", "")) != "sandbox_execution":
            continue
        details = payload.get("details")
        if not isinstance(details, dict):
            continue
        ts = parse_ts(details.get("timestamp") or payload.get("timestamp"))
        rows.append(
            {
                "timestamp": ts,
                "command": str(details.get("command", "")),
                "success": bool(details.get("success", False)),
                "exit_code": details.get("exit_code"),
                "execution_time": float(details.get("execution_time", 0.0) or 0.0),
                "error": str(details.get("error", "")),
                "output": str(details.get("output", "")),
                "workdir": str(details.get("workdir", "/workspace")),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["timestamp"].notna()].sort_values("timestamp")
    return df


def parse_decisions(decision_rows: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in decision_rows:
        payload = safe_json(raw)
        ts = parse_ts(payload.get("timestamp"))
        rows.append(
            {
                "timestamp": ts,
                "event_type": str(payload.get("event_type", "")),
                "source": str(payload.get("source", "")),
                "user_id": str(payload.get("user_id", "")),
                "summary": str(payload.get("summary", "")),
                "details": json.dumps(payload.get("details", {}), ensure_ascii=True),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df["timestamp"].notna()].sort_values("timestamp", ascending=False)
    return df


def get_recent_chats(redis_client, limit: int = 200) -> list[dict[str, Any]]:
    if not redis_client:
        return []
    try:
        chats: list[dict[str, Any]] = []
        for key in redis_client.scan_iter(match="her:context:*", count=500):
            size = _context_message_count(redis_client, key)
            if size <= 0:
                continue
            head = _context_entries(redis_client, key, limit=3)
            last_role = "unknown"
            last_message = ""
            for raw in head:
                role = str(raw.get("role", "unknown"))
                message = str(raw.get("message", ""))
                if message:
                    last_role = role
                    last_message = message
                    break
            chats.append(
                {
                    "context_key": key,
                    "message_count": size,
                    "last_role": last_role,
                    "last_message": last_message[:240],
                    "is_group": "group:" in key,
                }
            )
            if len(chats) >= limit:
                break
        chats.sort(key=lambda x: x["message_count"], reverse=True)
        return chats
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Error fetching recent chats: {exc}")
        return []


def get_short_memory_stats(redis_client, recent_chats: list[dict[str, Any]]) -> dict[str, Any]:
    if not redis_client:
        return {}
    try:
        total_threads = len(recent_chats)
        group_threads = sum(1 for item in recent_chats if item["is_group"])
        user_threads = total_threads - group_threads
        total_messages = sum(int(item["message_count"]) for item in recent_chats)

        role_counts: Counter[str] = Counter()
        sample_checked = 0
        for item in recent_chats[:100]:
            sample_checked += 1
            key = item["context_key"]
            for parsed in _context_entries(redis_client, key, limit=20):
                role_counts[str(parsed.get("role", "unknown"))] += 1

        top_threads = pd.DataFrame(recent_chats[:20]) if recent_chats else pd.DataFrame()
        return {
            "threads_total": total_threads,
            "threads_user": user_threads,
            "threads_group": group_threads,
            "messages_total": total_messages,
            "role_counts": dict(role_counts),
            "sample_threads_checked": sample_checked,
            "top_threads_df": top_threads,
        }
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Error computing short-memory stats: {exc}")
        return {}


def get_memory_stats(pg_conn):
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
            cursor.execute(
                """
                SELECT CAST(user_id AS TEXT) AS user_id, COUNT(*) AS c
                FROM memories
                GROUP BY CAST(user_id AS TEXT)
                ORDER BY c DESC
                LIMIT 15
                """
            )
            top_users = [{"user_id": row[0], "count": row[1]} for row in cursor.fetchall()]
        elif "payload" in memory_columns:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT payload->>'user_id')
                FROM memories
                WHERE payload->>'user_id' IS NOT NULL
                """
            )
            users_with_memories = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT COALESCE(payload->>'user_id', 'unknown') AS user_id, COUNT(*) AS c
                FROM memories
                GROUP BY COALESCE(payload->>'user_id', 'unknown')
                ORDER BY c DESC
                LIMIT 15
                """
            )
            top_users = [{"user_id": row[0], "count": row[1]} for row in cursor.fetchall()]
        else:
            users_with_memories = 0
            top_users = []

        if "category" in memory_columns:
            cursor.execute(
                """
                SELECT COALESCE(category, 'uncategorized') AS category, COUNT(*) AS count
                FROM memories
                GROUP BY COALESCE(category, 'uncategorized')
                ORDER BY count DESC
                LIMIT 20
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
                LIMIT 20
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
                ORDER BY date
                """
            )
            daily_memories = {str(row[0]): row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) FROM memories WHERE created_at > NOW() - INTERVAL '24 hours'")
            memories_24h = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT created_at,
                       COALESCE(memory_text, payload->>'memory', payload->>'text', payload::text) AS memory_text,
                       COALESCE(category, payload->'metadata'->>'category', 'uncategorized') AS category
                FROM memories
                ORDER BY created_at DESC NULLS LAST
                LIMIT 50
                """
            )
            recent_rows = [
                {
                    "created_at": row[0],
                    "memory_text": str(row[1])[:300],
                    "category": row[2],
                }
                for row in cursor.fetchall()
            ]
        else:
            daily_memories = {}
            memories_24h = 0
            recent_rows = []

        avg_importance = None
        if "importance_score" in memory_columns:
            cursor.execute("SELECT AVG(importance_score) FROM memories")
            avg_importance = cursor.fetchone()[0]
        elif "payload" in memory_columns:
            cursor.execute(
                """
                SELECT AVG((payload->'metadata'->>'importance')::float)
                FROM memories
                WHERE (payload->'metadata'->>'importance') IS NOT NULL
                """
            )
            avg_importance = cursor.fetchone()[0]

        cursor.close()
        return {
            "total_memories": total_memories,
            "users_with_memories": users_with_memories,
            "category_counts": category_counts,
            "daily_memories": daily_memories,
            "top_users": top_users,
            "memories_24h": memories_24h,
            "avg_importance": float(avg_importance) if avg_importance is not None else None,
            "recent_rows": recent_rows,
        }
    except Exception as exc:  # noqa: BLE001
        try:
            pg_conn.rollback()
        except Exception:
            pass
        st.warning(f"Error fetching memory stats: {exc}")
        return {}


def summarize_mcp_from_logs(log_df: pd.DataFrame) -> dict[str, Any]:
    if log_df.empty:
        return {"total_errors": 0, "by_server": {}, "top_messages": {}, "timeline": pd.DataFrame()}

    mcp_df = log_df[log_df["message"].str.contains("MCP|JSONRPC|mcp", case=False, na=False)].copy()
    if mcp_df.empty:
        return {"total_errors": 0, "by_server": {}, "top_messages": {}, "timeline": pd.DataFrame()}

    errors_df = mcp_df[mcp_df["level"].isin(["ERROR", "WARNING"])].copy()

    server_counts: defaultdict[str, int] = defaultdict(int)
    top_messages: Counter[str] = Counter()
    for message in errors_df["message"].tolist():
        top_messages[str(message)] += 1
        if "Failed to start MCP server '" in message:
            server = message.split("Failed to start MCP server '", 1)[1].split("'", 1)[0]
            server_counts[server] += 1

    if not errors_df.empty:
        errors_df["hour"] = errors_df["timestamp"].dt.floor("h")
        timeline = errors_df.groupby("hour").size().reset_index(name="errors")
    else:
        timeline = pd.DataFrame()

    return {
        "total_errors": int(len(errors_df)),
        "by_server": dict(server_counts),
        "top_messages": dict(top_messages.most_common(10)),
        "timeline": timeline,
    }


def render_capability_section(runtime_capabilities: dict[str, Any], capability_history: list[dict[str, Any]], log_df: pd.DataFrame):
    st.subheader("Capability Status")

    capabilities = runtime_capabilities.get("capabilities", {}) if runtime_capabilities else {}
    mcp_servers = runtime_capabilities.get("mcp_servers", {}) if runtime_capabilities else {}

    cap_col1, cap_col2, cap_col3 = st.columns(3)

    internet = capabilities.get("internet", {})
    sandbox = capabilities.get("sandbox", {})
    mcp_running = sum(1 for payload in mcp_servers.values() if payload.get("status") == "running")
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
        details_rows = [
            {"server": name, "status": data.get("status", "unknown"), "message": data.get("message", "")}
            for name, data in mcp_servers.items()
        ]
        st.dataframe(pd.DataFrame(details_rows), use_container_width=True, hide_index=True)

        degraded_rows = [row for row in details_rows if row["status"] not in {"running", "disabled"}]
        if degraded_rows:
            with st.expander("Recovery Hints", expanded=False):
                for row in degraded_rows:
                    if "timed out after 20s" in str(row["message"]):
                        st.write(
                            f"- `{row['server']}` timed out at 20s. Set `MCP_SERVER_START_TIMEOUT_SECONDS=60` "
                            "and rebuild `her-bot`."
                        )
                    else:
                        st.write(f"- `{row['server']}`: {row['message']}")
    else:
        st.warning("No runtime capability snapshot published yet.")

    if capability_history:
        hist_rows = []
        for snap in capability_history:
            ts = snap.get("_ts")
            caps = snap.get("capabilities", {}) or {}
            servers = snap.get("mcp_servers", {}) or {}
            hist_rows.append(
                {
                    "timestamp": ts,
                    "tool_count": int(snap.get("tool_count", 0) or 0),
                    "internet": 1 if (caps.get("internet", {}) or {}).get("available") else 0,
                    "sandbox": 1 if (caps.get("sandbox", {}) or {}).get("available") else 0,
                    "mcp_running": sum(1 for s in servers.values() if s.get("status") == "running"),
                    "mcp_total": len(servers),
                }
            )
        hist_df = pd.DataFrame(hist_rows)
        if not hist_df.empty:
            hist_df = hist_df.sort_values("timestamp")
            st.markdown("**Capability History (startup snapshots)**")
            render_plotly_line(hist_df, "timestamp", ["tool_count", "mcp_running"], "Tool & MCP Running Trend")

    mcp_summary = summarize_mcp_from_logs(log_df)
    if mcp_summary["total_errors"] > 0:
        st.markdown("**MCP Error Diagnostics**")
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            st.metric("MCP Errors/Warnings (logs)", mcp_summary["total_errors"])
            if mcp_summary["by_server"]:
                server_df = pd.DataFrame(
                    [{"server": k, "count": v} for k, v in mcp_summary["by_server"].items()]
                ).sort_values("count", ascending=False)
                render_plotly_bar(server_df, "server", "count", "MCP Errors by Server")
        with dcol2:
            if not mcp_summary["timeline"].empty:
                render_plotly_line(mcp_summary["timeline"], "hour", "errors", "MCP Errors Over Time")
            if mcp_summary["top_messages"]:
                st.dataframe(
                    pd.DataFrame(
                        [{"message": k, "count": v} for k, v in mcp_summary["top_messages"].items()]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )


with st.sidebar:
    st.title("HER Dashboard")
    st.markdown("---")

    auto_refresh = st.checkbox("Auto-refresh", value=True)
    if auto_refresh:
        refresh_interval = st.slider("Refresh interval (seconds)", 1, 60, 5)
        st.session_state.refresh_interval = refresh_interval

    st.markdown("---")
    page = st.radio(
        "Select Page",
        [
            "Overview",
            "Recent Chats",
            "Logs",
            "Executors",
            "Jobs",
            "Decisions",
            "Metrics",
            "Memory",
            "System Health",
        ],
    )

    st.markdown("---")
    if st.button("Refresh Now"):
        st.cache_resource.clear()
        st.rerun()

redis_client = get_redis_client()
pg_conn = get_postgres_connection()
metrics = get_metrics(redis_client)
runtime_capabilities = get_runtime_capabilities(redis_client)
capability_history = get_runtime_capability_history(redis_client)
scheduler_state = get_scheduler_state(redis_client)
recent_chats = get_recent_chats(redis_client, limit=200)
short_memory = get_short_memory_stats(redis_client, recent_chats)
memory_stats = get_memory_stats(pg_conn)
user_timezone_stats = get_user_timezone_stats(pg_conn)

events_df = parse_events(metrics.get("events", []))
logs_df = parse_logs(metrics.get("logs", []))
exec_df = parse_execs(metrics.get("sandbox_executions", []))
jobs_df = pd.DataFrame([safe_json(row) for row in metrics.get("scheduled_jobs", [])])
decision_df = parse_decisions(metrics.get("decision_logs", []))
reminder_event_df = parse_reminder_events(metrics.get("decision_logs", []))
timezone_conversion_df = parse_timezone_conversions(metrics.get("decision_logs", []))
if exec_df.empty:
    exec_df = parse_execs_from_decisions(metrics.get("decision_logs", []))

if page == "Overview":
    st.title("Overview Dashboard")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Messages", metrics.get("total_messages", 0))
    col2.metric("Total Tokens", f"{metrics.get('total_tokens', 0):,}")
    col3.metric("Unique Users", metrics.get("unique_users", 0))
    col4.metric("Long Memories", memory_stats.get("total_memories", 0))

    st.markdown("---")
    render_capability_section(runtime_capabilities, capability_history, logs_df)

    st.markdown("---")
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        st.subheader("Traffic Trend")
        if not events_df.empty:
            trend = events_df.copy()
            trend["hour"] = trend["timestamp"].dt.floor("h")
            agg = trend.groupby("hour", as_index=False).agg(messages=("user_id", "count"), tokens=("token_estimate", "sum"))
            render_plotly_line(agg, "hour", ["messages", "tokens"], "Messages & Tokens by Hour")
        else:
            st.info("No interaction events yet.")

    with pcol2:
        st.subheader("Log Levels")
        if not logs_df.empty:
            level_counts = logs_df["level"].value_counts()
            level_df = level_counts.rename_axis("level").reset_index(name="count")
            render_plotly_bar(level_df, "level", "count", "Log Levels")
        else:
            st.info("No logs available yet.")

    st.markdown("---")
    mcol1, mcol2 = st.columns(2)
    with mcol1:
        st.subheader("Short Memory (Redis Context)")
        st.metric("Threads", short_memory.get("threads_total", 0))
        st.metric("Messages Stored", short_memory.get("messages_total", 0))
        st.caption(
            f"User threads: {short_memory.get('threads_user', 0)} | "
            f"Group threads: {short_memory.get('threads_group', 0)}"
        )
        if short_memory.get("role_counts"):
            role_df = pd.DataFrame(
                [{"role": k, "entries": v} for k, v in short_memory["role_counts"].items()]
            ).sort_values("entries", ascending=False)
            render_plotly_bar(role_df, "role", "entries", "Context Roles")

    with mcol2:
        st.subheader("Long Memory (PostgreSQL)")
        st.metric("Total Memories", memory_stats.get("total_memories", 0))
        st.metric("Last 24h", memory_stats.get("memories_24h", 0))
        avg_importance = memory_stats.get("avg_importance")
        st.metric("Avg Importance", f"{avg_importance:.2f}" if isinstance(avg_importance, float) else "N/A")
        if memory_stats.get("category_counts"):
            category_df = pd.DataFrame(
                [{"category": k, "count": v} for k, v in memory_stats["category_counts"].items()]
            ).sort_values("count", ascending=False)
            render_plotly_bar(category_df, "category", "count", "Memory Categories")

elif page == "Logs":
    st.title("System Logs")

    log_level = st.selectbox("Filter by Level", ["All", "INFO", "WARNING", "ERROR", "DEBUG"])
    search_term = st.text_input("Search logs", "")

    if logs_df.empty:
        st.info("No logs available. Logs are stored in Redis under 'her:logs'.")
    else:
        filtered = logs_df.copy()
        if log_level != "All":
            filtered = filtered[filtered["level"] == log_level]
        if search_term:
            filtered = filtered[filtered["message"].str.contains(search_term, case=False, na=False)]

        st.subheader(f"Recent Logs ({len(filtered)} entries)")
        view = filtered.sort_values("timestamp", ascending=False).head(200)
        st.dataframe(view[["timestamp", "level", "message"]], use_container_width=True, hide_index=True)

        mcp_summary = summarize_mcp_from_logs(logs_df)
        st.markdown("---")
        st.subheader("MCP Failure Report")
        st.metric("MCP Errors/Warnings", mcp_summary["total_errors"])
        if mcp_summary["by_server"]:
            server_df = pd.DataFrame(
                [{"server": k, "count": v} for k, v in mcp_summary["by_server"].items()]
            ).sort_values("count", ascending=False)
            render_plotly_bar(server_df, "server", "count", "MCP Failures by Server")
        if mcp_summary["top_messages"]:
            st.dataframe(
                pd.DataFrame([{"message": k, "count": v} for k, v in mcp_summary["top_messages"].items()]),
                use_container_width=True,
                hide_index=True,
            )

elif page == "Recent Chats":
    st.title("Recent Chats")

    if not events_df.empty:
        st.subheader("Recent Interaction Events")
        preview = events_df.sort_values("timestamp", ascending=False).head(50).copy()
        preview["user_message"] = preview["user_message"].str.slice(0, 160)
        preview["response_message"] = preview["response_message"].str.slice(0, 160)
        st.dataframe(preview, use_container_width=True, hide_index=True)
    else:
        st.info("No interaction events found yet.")

    st.markdown("---")
    st.subheader("Redis Context Threads")
    if recent_chats:
        chats_df = pd.DataFrame(recent_chats)
        st.dataframe(chats_df[["context_key", "message_count", "last_role", "last_message", "is_group"]], use_container_width=True, hide_index=True)
    else:
        st.info("No Redis context threads found yet.")

    st.markdown("---")
    st.subheader("Behind The Chat: Reasoning / Tool Trace")
    if decision_df.empty:
        st.info("No decision trace events yet.")
    else:
        trace = decision_df[
            decision_df["event_type"].isin(
                [
                    "assistant_response",
                    "tool_call",
                    "tool_result",
                    "natural_schedule_created",
                    "reinforcement_event",
                    "scheduler_execution",
                ]
            )
        ].copy()
        if trace.empty:
            st.info("No reasoning/tool trace events yet.")
        else:
            st.dataframe(
                trace[["timestamp", "event_type", "source", "user_id", "summary", "details"]].head(300),
                use_container_width=True,
                hide_index=True,
            )

elif page == "Executors":
    st.title("Sandbox Executors")

    if exec_df.empty:
        st.info("No sandbox executions recorded yet. Executions are logged to Redis under 'her:sandbox:executions'.")
    else:
        latest = exec_df.sort_values("timestamp", ascending=False)
        success_rate = float(latest["success"].mean() * 100.0)
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Executions", len(latest))
        col2.metric("Successful", int(latest["success"].sum()))
        col3.metric("Success Rate", f"{success_rate:.1f}%")

        st.markdown("---")
        st.subheader("Execution Trend")
        trend = latest.copy()
        trend["hour"] = trend["timestamp"].dt.floor("h")
        agg = trend.groupby("hour", as_index=False).agg(total=("command", "count"), failures=("success", lambda s: int((~s).sum())))
        render_plotly_line(agg, "hour", ["total", "failures"], "Sandbox Execution Trend")

        st.markdown("---")
        st.subheader("Recent Execution Details")
        st.dataframe(
            latest[["timestamp", "command", "success", "exit_code", "execution_time", "workdir"]].head(100),
            use_container_width=True,
            hide_index=True,
        )

elif page == "Jobs":
    st.title("Scheduled Jobs")
    st.subheader("Timezone Panel")
    tz_col1, tz_col2 = st.columns(2)
    with tz_col1:
        st.metric("System TZ", os.getenv("TZ", "UTC"))
        st.metric("Default User TZ", os.getenv("USER_TIMEZONE", "UTC"))
    with tz_col2:
        st.metric("Active Users with TZ", len(user_timezone_stats))
        if user_timezone_stats:
            tz_df = pd.DataFrame(user_timezone_stats)
            st.dataframe(tz_df[["user_id", "user_timezone", "chat_id"]].head(20), use_container_width=True, hide_index=True)
    if not timezone_conversion_df.empty:
        st.markdown("**Recent Reminder Conversions**")
        st.dataframe(
            timezone_conversion_df[["timestamp", "user_id", "user_timezone", "local_time", "stored_utc"]].head(50),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No timezone conversion events found yet.")

    st.subheader("Upcoming Jobs")
    upcoming = scheduler_state.get("upcoming", []) if scheduler_state else []
    if upcoming:
        upcoming_df = pd.DataFrame(upcoming)
        if "next_run" in upcoming_df.columns:
            upcoming_df["next_run"] = upcoming_df["next_run"].apply(parse_ts)
            upcoming_df = upcoming_df.sort_values("next_run")
        st.dataframe(upcoming_df.head(100), use_container_width=True, hide_index=True)
    else:
        st.info("No upcoming scheduler state found. Key: `her:scheduler:state`")

    st.markdown("---")
    st.subheader("Execution History")
    if jobs_df.empty:
        st.info("No scheduled jobs executed yet. Jobs are logged to Redis under 'her:scheduler:jobs'.")
    else:
        jobs_df["timestamp"] = jobs_df.get("timestamp", "").apply(parse_ts)
        jobs_df = jobs_df.sort_values("timestamp", ascending=False)
        st.dataframe(jobs_df.head(100), use_container_width=True, hide_index=True)
        if "success" in jobs_df.columns:
            success_df = (
                jobs_df["success"]
                .value_counts()
                .rename(index={True: "success", False: "failed"})
                .rename_axis("status")
                .reset_index(name="count")
            )
            render_plotly_bar(success_df, "status", "count", "Scheduled Job Outcomes")

    st.markdown("---")
    st.subheader("Reminder State Table")
    if not reminder_event_df.empty:
        st.dataframe(
            reminder_event_df[
                ["timestamp", "reminder_id", "old_status", "new_status", "retry_count", "max_retries", "last_error", "chat_id"]
            ].head(150),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No reminder state transitions recorded yet.")

    st.markdown("---")
    st.subheader("Reasoning Flow Viewer")
    if decision_df.empty:
        st.info("No reasoning flow events yet.")
    else:
        reasoning_trace = decision_df[decision_df["event_type"].isin(["agent_step", "autonomous_operator_action"])].copy()
        if reasoning_trace.empty:
            st.info("No agent step traces found yet.")
        else:
            st.dataframe(
                reasoning_trace[["timestamp", "event_type", "summary", "details"]].head(150),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("---")
    st.subheader("Failure Heatmap")
    if reminder_event_df.empty:
        st.info("No reminder failures available for heatmap.")
    else:
        failures = reminder_event_df[reminder_event_df["new_status"].isin(["FAILED", "RETRY"])].copy()
        if failures.empty:
            st.info("No reminder failures detected.")
        else:
            failures["failure_type"] = failures["last_error"].apply(
                lambda text: "permanent" if "chat_not_found" in str(text).lower() or "forbidden" in str(text).lower() else "transient"
            )
            heat_df = failures.groupby(["new_status", "failure_type"], as_index=False).size().rename(columns={"size": "count"})
            render_plotly_bar(heat_df, "new_status", "count", "Reminder Failure Types")
            st.dataframe(heat_df, use_container_width=True, hide_index=True)

elif page == "Decisions":
    st.title("Decision Logs")
    if decision_df.empty:
        st.info("No decision logs yet. Events are stored under `her:decision:logs`.")
    else:
        st.dataframe(decision_df.head(300), use_container_width=True, hide_index=True)
        count_df = decision_df["event_type"].value_counts().rename_axis("event_type").reset_index(name="count")
        render_plotly_bar(count_df, "event_type", "count", "Decision Events by Type")

elif page == "Metrics":
    st.title("Detailed Metrics")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Messages", metrics.get("total_messages", 0))
    col2.metric("Total Tokens", f"{metrics.get('total_tokens', 0):,}")
    col3.metric("Unique Users", metrics.get("unique_users", 0))

    st.markdown("---")
    st.subheader("Token Usage Over Time")
    if not events_df.empty:
        token_trend = events_df.copy()
        token_trend["hour"] = token_trend["timestamp"].dt.floor("h")
        token_agg = token_trend.groupby("hour", as_index=False)["token_estimate"].sum()
        render_plotly_line(token_agg, "hour", "token_estimate", "Token Usage by Hour")

        st.markdown("---")
        st.subheader("Top Active Users")
        user_activity = events_df.groupby("user_id", as_index=False).agg(messages=("user_id", "count"), tokens=("token_estimate", "sum"))
        st.dataframe(user_activity.sort_values("messages", ascending=False).head(30), use_container_width=True, hide_index=True)
    else:
        st.info("No interaction metrics available yet.")

elif page == "Memory":
    st.title("Memory Statistics")

    left, right = st.columns(2)
    with left:
        st.subheader("Short Memory Report (Redis)")
        st.metric("Context Threads", short_memory.get("threads_total", 0))
        st.metric("Stored Messages", short_memory.get("messages_total", 0))
        st.caption(
            f"Role sample based on {short_memory.get('sample_threads_checked', 0)} recent threads."
        )
        if short_memory.get("role_counts"):
            role_df = pd.DataFrame(
                [{"role": k, "count": v} for k, v in short_memory["role_counts"].items()]
            ).sort_values("count", ascending=False)
            render_plotly_bar(role_df, "role", "count", "Role Distribution")

        top_threads_df = short_memory.get("top_threads_df")
        if isinstance(top_threads_df, pd.DataFrame) and not top_threads_df.empty:
            st.markdown("**Largest Context Threads**")
            st.dataframe(
                top_threads_df[["context_key", "message_count", "is_group", "last_role", "last_message"]],
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.subheader("Long Memory Report (PostgreSQL)")
        st.metric("Total Memories", memory_stats.get("total_memories", 0))
        st.metric("Users with Memories", memory_stats.get("users_with_memories", 0))
        st.metric("Memories (24h)", memory_stats.get("memories_24h", 0))

        avg_importance = memory_stats.get("avg_importance")
        st.metric("Average Importance", f"{avg_importance:.2f}" if isinstance(avg_importance, float) else "N/A")

        categories = memory_stats.get("category_counts", {})
        if categories:
            st.markdown("**Categories**")
            category_df = pd.DataFrame(
                [{"category": k, "count": v} for k, v in categories.items()]
            ).sort_values("count", ascending=False)
            render_plotly_bar(category_df, "category", "count", "Memory Categories")

    st.markdown("---")
    st.subheader("Long Memory Growth (Last 30 Days)")
    daily = memory_stats.get("daily_memories", {})
    if daily:
        daily_df = pd.DataFrame(list(daily.items()), columns=["date", "count"]).sort_values("date")
        render_plotly_line(daily_df, "date", "count", "Long-Memory Growth (30d)")
    else:
        st.info("No long-memory growth data available yet.")

    st.markdown("---")
    st.subheader("Top Long-Memory Users")
    top_users = memory_stats.get("top_users", [])
    if top_users:
        st.dataframe(pd.DataFrame(top_users), use_container_width=True, hide_index=True)
    else:
        st.info("No per-user memory distribution found.")

    st.markdown("---")
    st.subheader("Recent Long-Memory Entries")
    recent_rows = memory_stats.get("recent_rows", [])
    if recent_rows:
        st.dataframe(pd.DataFrame(recent_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No recent long-memory rows found.")

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
                    LIMIT 50
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
                    LIMIT 50
                    """,
                    (f"%{search_query}%",),
                )
            else:
                cursor.close()
                st.info("Memories table is present but not in a searchable schema.")
                results = []

            if "memory_text" in memory_columns or "payload" in memory_columns:
                results = cursor.fetchall()
                cursor.close()

            if results:
                result_df = pd.DataFrame(results, columns=["text", "category", "created_at", "importance"])
                st.dataframe(result_df, use_container_width=True, hide_index=True)
            else:
                st.info("No memories found")
        except Exception as exc:  # noqa: BLE001
            try:
                pg_conn.rollback()
            except Exception:
                pass
            st.error(f"Search error: {exc}")

elif page == "System Health":
    st.title("System Health")

    scol1, scol2 = st.columns(2)
    with scol1:
        st.write("**Redis**")
        if redis_client:
            try:
                redis_client.ping()
                info = redis_client.info()
                st.success("Connected")
                st.text(f"Version: {info.get('redis_version', 'N/A')}")
                st.text(f"Used Memory: {info.get('used_memory_human', 'N/A')}")
                st.text(f"Connected clients: {info.get('connected_clients', 'N/A')}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error: {exc}")
        else:
            st.error("Not connected")

    with scol2:
        st.write("**PostgreSQL**")
        if pg_conn:
            try:
                cursor = pg_conn.cursor()
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                cursor.close()
                st.success("Connected")
                st.text(f"Version: {version[:80]}...")
                st.text(f"DB: {POSTGRES_DB} @ {POSTGRES_HOST}:{POSTGRES_PORT}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error: {exc}")
        else:
            st.error("Not connected")

    st.markdown("---")
    st.subheader("Runtime Capability Snapshot")
    if runtime_capabilities:
        st.json(runtime_capabilities)
    else:
        st.info("No capability snapshot found. The bot publishes this under `her:runtime:capabilities` after startup.")

    st.markdown("---")
    st.subheader("Environment")
    ecol1, ecol2 = st.columns(2)
    with ecol1:
        st.write(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
        st.write(f"LLM Provider: {os.getenv('LLM_PROVIDER', 'ollama')}")
        st.write(f"Redis Host: {REDIS_HOST}")
    with ecol2:
        st.write(f"Postgres Host: {POSTGRES_HOST}")
        st.write(f"Postgres DB: {POSTGRES_DB}")
        st.write(f"Last Check: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

if auto_refresh:
    import time

    time.sleep(st.session_state.refresh_interval)
    st.rerun()
