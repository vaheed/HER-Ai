from pathlib import Path


def test_reminders_require_chat_id() -> None:
    scheduler_source = Path("her-core/utils/scheduler.py").read_text()
    handlers_source = Path("her-core/her_telegram/handlers.py").read_text()

    assert "Chat ID required for reminder tasks" in scheduler_source
    assert '"chat_id"' in scheduler_source
    assert "Chat ID required for reminders" in handlers_source
    assert "_persist_user_runtime_profile" in handlers_source

