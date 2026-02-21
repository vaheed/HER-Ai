from pathlib import Path


def test_reminder_state_machine_and_backoff_rules_exist() -> None:
    scheduler_source = Path("her-core/utils/scheduler.py").read_text()

    assert "_execute_reminder_task" in scheduler_source
    assert '"status"' in scheduler_source
    assert "PENDING" in scheduler_source
    assert "RETRY" in scheduler_source
    assert "FAILED" in scheduler_source
    assert "SENT" in scheduler_source
    assert "max_retries" in scheduler_source
    assert "reminder_retry" in scheduler_source
