# Example Scenarios and Prompt Library

The prompt library is designed for onboarding, validation, and regression testing of assistant behavior.

## Library Structure

Prompt categories mirror in-code examples in `her-core/her_telegram/handlers.py` (`_EXAMPLE_PROMPTS`):
- chat
- memory
- scheduling
- automation
- web
- mcp_tools
- sandbox
- admin
- personality
- productivity

Telegram shortcuts:
- `/example`
- `/example all`
- `/example <topic>`

## Example Scenarios

## 1. Conversational continuity
```text
Remember that I prefer concise replies.
What should I focus on this afternoon?
```

## 2. Reminder scheduling
```text
Remind me in 45 minutes to send the draft.
```

## 3. Rule-based automation
```text
Check BTC every 5 minutes and notify me if it rises 8%.
```

## 4. Tool-assisted diagnostics
```text
Check SSL expiry for github.com and summarize result.
```

## 5. Admin operations
```text
/schedule list
/mcp
```

## Prompt Quality Guidelines

- Be explicit about timeframe, threshold, and expected output format.
- For workflows, include source URL and clear condition.
- For diagnostics, specify host/domain and desired summary level.
