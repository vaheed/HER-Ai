# HER Capability Testing Playbook (Step-by-Step)

Use this guide to validate HER end-to-end after startup. It is intentionally hands-on and organized by capability.

## 0) Prerequisites

- `.env` configured (at minimum: `TELEGRAM_BOT_TOKEN`, `ADMIN_USER_ID`, provider keys/settings, DB/Redis passwords).
- Docker daemon running.
- You are at repository root.

## 1) Bring the stack up

```bash
docker compose up -d --build
```

Then check runtime health:

```bash
docker compose ps
docker compose logs --tail=100 her-bot
```

### Expected

- `her-bot`, `postgres`, `redis`, `dashboard` are up.
- `her-bot` logs include startup milestones for memory + agent initialization.

---

## 2) Validate HTTP health endpoint

```bash
curl -sS http://localhost:8000
```

### Expected

```json
{"status": "ok"}
```

---

## 3) Validate Telegram baseline behavior

Open your bot in Telegram and execute these tests in order.

### 3.1 `/start` works

Send:

```text
/start
```

Expected:
- Welcome message.
- If your Telegram user ID is in admin list, an admin inline menu appears.

### 3.2 `/help` returns mode-appropriate commands

Send:

```text
/help
```

Expected:
- Admin sees admin command list.
- Public user sees public command list.

### 3.3 Conversational response path works

Send:

```text
Hello HER, can you remember that I like jasmine tea?
```

Expected:
- Bot sends a normal conversational reply.
- A follow-up message in same chat should keep continuity.

---

## 4) Validate admin command set

> Run as admin user.

### 4.1 `/status`

Expected:
- Status response is returned.
- Includes MCP status block when MCP manager is loaded.

### 4.2 `/personality`

Expected:
- Inline keyboard for personality adjustments is displayed.

### 4.3 `/memories`

Expected:
- Response includes recent context/memory info.

### 4.4 `/mcp`

Expected:
- MCP server status payload returned (running/failed/disabled per server).

### 4.5 `/reset`

Expected:
- Reset acknowledgement is returned.

### 4.6 `/schedule`

Run:

```text
/schedule list
```

Expected:
- Scheduled tasks list is returned with interval and enabled state.

Run:

```text
/schedule run memory_reflection
```

Expected:
- Immediate execution acknowledgement is returned.

---

## 5) Validate public-mode throttling

> Run as non-admin user.

- Send messages quickly (more than configured per-minute cap in `config/rate_limits.yaml`).

Expected:
- Messages above threshold are rejected with rate-limit notice.

---

## 6) Validate MCP-backed capabilities

### 6.1 Confirm configured servers

```bash
sed -n '1,200p' config/mcp_servers.yaml
```

Expected:
- `fetch`, `filesystem`, `postgres`, `memory`, `sequential-thinking`, and `pdf` enabled by default.
- `brave-search` and `puppeteer` disabled by default unless you explicitly enable them.

### 6.2 Web-search intent test (Telegram)

Send:

```text
Search the web for latest AI safety news and summarize in 3 bullets.
```

Expected:
- Bot returns a concise summary.
- If MCP web search server fails to start, status should reveal failure reason.

### 6.3 File operation intent test (if wired into your runtime prompts)

Send:

```text
Read /workspace/notes.txt and summarize it.
```

Expected:
- If file tool is available to the active path, reply includes file summary.
- If unavailable, bot should fail gracefully and continue responding.

---

## 7) Validate dashboard visibility

Open:

- `http://localhost:8501`

Expected:
- Dashboard loads.
- Core service health/metrics are visible.

---

## 8) Negative-path checks

### 8.1 Telegram token missing

Set `TELEGRAM_BOT_TOKEN` empty and restart `her-bot`.

Expected:
- Service should stay up without polling.
- Logs warn that token is missing.

### 8.2 Memory backend pressure

Simulate low-memory model or broken provider config.

Expected:
- With fail-open memory mode, HER still replies using short-term context.
- Warnings appear in logs rather than hard crash.

---

## 9) Quick regression checklist

- [ ] `docker compose ps` all required services healthy.
- [ ] `/start` and `/help` work.
- [ ] Admin commands return responses.
- [ ] Public throttling triggers when expected.
- [ ] `/mcp` reports server statuses.
- [ ] `/schedule list` returns configured tasks.
- [ ] Dashboard reachable at `:8501`.
- [ ] No crash loops in `docker compose logs her-bot`.

---

## Notes

- For runtime behavior details and current file locations, see `README.md` and `docs/mcp_guide.md`.
- For planned/unfinished work, see `docs/roadmap.md`.
