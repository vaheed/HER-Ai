import os
from datetime import datetime

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

st.subheader("Last Updated")
st.write(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
