# Folder Reference: dashboard

## Purpose

Streamlit-based operational dashboard for monitoring runtime activity.

## Files

- `dashboard/app.py` - full dashboard UI and data queries
- `dashboard/requirements.txt` - dashboard dependencies
- `dashboard/Dockerfile` - dashboard image build

## Behavior

Dashboard reads Redis keys for logs/metrics/runtime state and PostgreSQL for memory statistics/search.

## How to Run and Test

```bash
docker compose up -d dashboard
```

Access:
- `http://localhost:8501`

Validate logs:
```bash
docker compose logs --tail=200 dashboard
```
