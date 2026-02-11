import yaml
from pathlib import Path


def test_crew_tasks_define_expected_output() -> None:
    source = Path("her-core/agents/crew_orchestrator.py").read_text()
    assert source.count("expected_output=") >= 3


def test_telegram_run_polling_disables_thread_signal_handlers() -> None:
    source = Path("her-core/telegram_bot.py").read_text()
    assert "stop_signals=None" in source


def test_compose_supports_pull_and_build_for_runtime_services() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text())
    services = compose["services"]
    assert "image" in services["her-bot"] and "build" in services["her-bot"]
    assert "image" in services["dashboard"] and "build" in services["dashboard"]
    assert "image" in services["sandbox"] and "build" in services["sandbox"]
