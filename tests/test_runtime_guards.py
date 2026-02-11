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


def test_telegram_run_polling_retries_on_network_timeouts() -> None:
    source = Path("her-core/telegram_bot.py").read_text()
    assert "except (TimedOut, NetworkError)" in source
    assert "TELEGRAM_STARTUP_RETRY_DELAY_SECONDS" in Path(".env.example").read_text()


def test_telegram_can_be_disabled_via_env_flag() -> None:
    source = Path("her-core/main.py").read_text()
    assert "config.telegram_enabled and config.telegram_bot_token" in source
    assert "TELEGRAM_ENABLED" in Path(".env.example").read_text()


def test_telegram_generates_agentic_replies_via_llm() -> None:
    source = Path("her-core/telegram_bot.py").read_text()
    assert "llm = build_llm()" in source
    assert "memory.search_memories(user_id, message_text, limit=5)" in source
    assert "llm.invoke(" in source
    assert "HER received your message and saved it to memory" not in source
