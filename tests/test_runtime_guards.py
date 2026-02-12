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


def test_telegram_public_mode_controls_are_configured() -> None:
    source = Path("her-core/telegram_bot.py").read_text()
    config_source = Path("her-core/config.py").read_text()
    env_example = Path(".env.example").read_text()

    assert "TelegramAccessController" in source
    assert "CommandHandler(\"approve\"" in source
    assert "CommandHandler(\"mode\"" in source
    assert "telegram_public_approval_required" in config_source
    assert "telegram_public_rate_limit_per_minute" in config_source
    assert "TELEGRAM_PUBLIC_APPROVAL_REQUIRED=true" in env_example
    assert "TELEGRAM_PUBLIC_RATE_LIMIT_PER_MINUTE=20" in env_example


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


def test_telegram_retries_transient_llm_failures_and_parses_retry_hints() -> None:
    source = Path("her-core/telegram_bot.py").read_text()
    assert "_extract_retry_after_seconds" in source
    assert "retry_on=(RateLimitError, APITimeoutError, APIConnectionError)" in source
    assert "I'm temporarily rate-limited by the model provider." in source


def test_openrouter_provider_is_supported_for_chat_and_memory() -> None:
    llm_factory_source = Path("her-core/utils/llm_factory.py").read_text()
    mem_source = Path("her-core/memory/mem0_client.py").read_text()
    config_source = Path("her-core/config.py").read_text()
    env_example = Path(".env.example").read_text()

    assert 'if provider == "openrouter"' in llm_factory_source
    assert 'OPENROUTER_API_KEY' in env_example
    assert 'OPENROUTER_MODEL' in env_example
    assert 'OPENROUTER_API_BASE' in env_example
    assert 'openrouter_api_key' in config_source
    assert 'if config.llm_provider == "openrouter"' in mem_source


def test_web_search_uses_no_key_curl_fallback() -> None:
    tools_source = Path("her-core/her_mcp/tools.py").read_text()
    helpers_source = Path("her-core/her_mcp/helpers.py").read_text()

    assert "class CurlWebSearchTool" in tools_source
    assert "api.duckduckgo.com" in tools_source
    assert "subprocess.run(" in tools_source
    assert "CurlWebSearchTool()" in tools_source
    assert 'tool_name="brave_web_search"' not in tools_source
    assert "api.duckduckgo.com" in helpers_source


def test_entrypoint_skips_config_seed_when_runtime_volume_is_readonly() -> None:
    source = Path("her-core/docker-entrypoint.sh").read_text()
    assert 'if [ -w "$RUNTIME_CONFIG_DIR" ]' in source
    assert 'skipping seed copy' in source
