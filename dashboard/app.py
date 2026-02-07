import json
import os
from datetime import datetime, timezone

import redis

import streamlit as st

st.set_page_config(page_title="HER Admin Dashboard", layout="wide")

st.title("HER Admin Dashboard")
st.caption("Phase 1 foundation dashboard placeholder for system readiness checks.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Service Status")
    st.write("✅ her-bot container running (check Docker)")
    st.write("✅ postgres container running (check Docker)")
    st.write("✅ redis container running (check Docker)")
    st.write("✅ sandbox container running (check Docker)")

with col2:
    st.subheader("Environment")
    st.write(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    st.write(f"LLM Provider: {os.getenv('LLM_PROVIDER', 'openai')}")
    st.write(f"Postgres Host: {os.getenv('POSTGRES_HOST', 'postgres')}")
    st.write(f"Redis Host: {os.getenv('REDIS_HOST', 'redis')}")

st.subheader("Quick Links")
st.write("- Docker Compose: `docker compose ps`")
st.write("- Logs: `docker compose logs -f her-bot`")

st.subheader("Usage Metrics")
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
redis_password = os.getenv("REDIS_PASSWORD", "")

try:
    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        decode_responses=True,
    )
    total_tokens = int(redis_client.get("her:metrics:tokens") or 0)
    total_messages = int(redis_client.get("her:metrics:messages") or 0)
    unique_users = int(redis_client.scard("her:metrics:users") or 0)
    last_response_raw = redis_client.get("her:metrics:last_response")
    events_raw = redis_client.lrange("her:metrics:events", 0, 9)
except redis.RedisError as exc:
    st.warning(f"Unable to load metrics from Redis: {exc}")
    total_tokens = 0
    total_messages = 0
    unique_users = 0
    last_response_raw = None
    events_raw = []

metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
metrics_col1.metric("Total Token Estimate", total_tokens)
metrics_col2.metric("Total Messages", total_messages)
metrics_col3.metric("Unique Users", unique_users)

if last_response_raw:
    st.markdown("**Last Response**")
    st.json(json.loads(last_response_raw))
else:
    st.info("No responses recorded yet.")

if events_raw:
    st.markdown("**Recent Activity**")
    st.table([json.loads(entry) for entry in events_raw])

st.subheader("Last Updated")
st.write(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
