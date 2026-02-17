# Code Area: her-core/her_telegram

## Purpose

Telegram interface layer, including command handlers, access control behavior, scheduling UX, and autonomous sandbox loop integration.

## Files

- `her-core/her_telegram/bot.py` - telegram app handler registration
- `her-core/her_telegram/handlers.py` - command + message handling logic
- `her-core/her_telegram/autonomous_operator.py` - JSON action execution loop
- `her-core/her_telegram/unified_interpreter.py` - interpretation helper
- `her-core/her_telegram/keyboards.py` - inline keyboard helpers
- `her-core/her_telegram/rate_limiter.py` - rate limiting

## How It Works

Incoming Telegram updates are routed to `MessageHandlers`, which manages admin/public paths, memory updates, LLM responses, scheduling intents, and tool actions.

## How to Test

```bash
pytest tests/test_runtime_guards.py -q
```
