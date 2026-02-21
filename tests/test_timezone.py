from pathlib import Path


def test_timezone_defaults_and_propagation_are_configured() -> None:
    env_source = Path(".env.example").read_text()
    config_source = Path("her-core/config.py").read_text()
    compose_source = Path("docker-compose.yml").read_text()
    scheduler_source = Path("her-core/utils/scheduler.py").read_text()

    assert "USER_TIMEZONE=UTC" in env_source
    assert "default_user_timezone" in config_source
    assert "- USER_TIMEZONE" in compose_source
    assert "default_user_tz" in scheduler_source


def test_reminder_time_conversion_and_audit_logging_exist() -> None:
    handlers_source = Path("her-core/her_telegram/handlers.py").read_text()
    assert "def _log_timezone_conversion" in handlers_source
    assert 'event_type="timezone_conversion"' in handlers_source
    assert "stored_utc" in handlers_source

