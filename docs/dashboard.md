# Admin Dashboard

The HER-Ai admin dashboard is a Streamlit app that provides operational visibility into
memory, health checks, and usage metrics. It is designed for administrators to tune
personality traits, review reflections, and monitor the system in real time.

## Where it lives
- Source code: `dashboard/app.py`
- Docker service: `her-dashboard` (see `docker-compose.yml`)

## Running locally
If you are not using Docker, you can start the dashboard with:

```bash
streamlit run dashboard/app.py
```

Make sure your environment variables match the values in `.env.example`, and that the
core services (PostgreSQL, Redis, and the HER core app) are running.

## Related documentation
- [Architecture Overview](architecture.md)
- [MCP Integration Guide](mcp_guide.md)
