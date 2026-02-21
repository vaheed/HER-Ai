from pathlib import Path


def test_reminder_state_machine_and_backoff_rules_exist() -> None:
    scheduler_source = Path("her-core/utils/scheduler.py").read_text()

    assert "_execute_reminder_state_machine" in scheduler_source
    assert '"status"' in scheduler_source
    assert "PENDING" in scheduler_source
    assert "RETRY" in scheduler_source
    assert "FAILED" in scheduler_source
    assert "SENT" in scheduler_source
    assert "backoff_seconds = 10 * (3 **" in scheduler_source
    assert "reminder_state_change" in scheduler_source

