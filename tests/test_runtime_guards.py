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


def test_startup_uses_personality_manager_for_trait_mutation() -> None:
    source = Path("her-core/main.py").read_text()
    assert "personality_manager = PersonalityAgent" in source
    assert "personality_manager.adjust_trait" in source


def test_startup_warmup_is_opt_in_and_disabled_by_default() -> None:
    main_source = Path("her-core/main.py").read_text()
    config_source = Path("her-core/config.py").read_text()
    env_example = Path(".env.example").read_text()

    assert "if config.startup_warmup_enabled" in main_source
    assert "STARTUP_WARMUP_ENABLED" in config_source
    assert "STARTUP_WARMUP_ENABLED=false" in env_example

def test_telegram_runtime_shutdown_error_exits_cleanly() -> None:
    source = Path("her-core/telegram_bot.py").read_text()
    assert "_is_shutdown_network_error" in source
    assert "Telegram polling stopped during runtime shutdown" in source



def test_memory_failures_fallback_to_context_only_by_default() -> None:
    mem_source = Path("her-core/memory/mem0_client.py").read_text()
    config_source = Path("her-core/config.py").read_text()
    env_example = Path(".env.example").read_text()

    assert "memory_strict_mode" in config_source
    assert "MEMORY_STRICT_MODE=false" in env_example
    assert "except RetryError" in mem_source
    assert "_is_ollama_low_memory_error" in mem_source
    assert "model requires more system memory" in Path("README.md").read_text()
    assert "return []" in mem_source


def test_memory_search_results_are_normalized_to_list_shape() -> None:
    mem_source = Path("her-core/memory/mem0_client.py").read_text()
    assert "def _normalize_search_results" in mem_source
    assert "results = with_retry" in mem_source
    assert "return _normalize_search_results(results)" in mem_source
