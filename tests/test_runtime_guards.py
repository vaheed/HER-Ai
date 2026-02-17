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


def test_telegram_handler_fails_over_to_ollama_on_502_503() -> None:
    handlers_source = Path("her-core/her_telegram/handlers.py").read_text()
    env_example = Path(".env.example").read_text()

    assert "if status_code in {502, 503}" in handlers_source
    assert "self._fallback_llm" in handlers_source
    assert "event_type=\"llm_failover\"" in handlers_source
    assert "Primary LLM provider '%s' failed with status %s; retrying with fallback '%s'" in handlers_source
    assert "LLM_ENABLE_FALLBACK=true" in env_example
    assert "LLM_FALLBACK_PROVIDER=ollama" in env_example


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
    assert "def _resolve_mem0_llm_provider" in mem_source
    assert 'return "openai"' in mem_source


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
    assert 'export HER_CONFIG_DIR="$DEFAULT_CONFIG_DIR"' in source


def test_config_resolution_checks_baked_defaults_before_repo_fallback() -> None:
    source = Path("her-core/utils/config_paths.py").read_text()
    assert 'Path("/app/config.defaults")' in source
    assert "prefer_defaults" in source
    assert "os.access(runtime_config_dir, os.W_OK)" in source
    assert 'return Path(__file__).resolve().parents[2] / "config" / filename' in source


def test_base_agent_re_resolves_missing_config_paths() -> None:
    source = Path("her-core/agents/base_agent.py").read_text()
    assert "resolve_config_file(path.name)" in source
    assert "Config file '{path.name}' not found." in source


def test_mcp_startup_cancellation_re_raises_and_cleans_up_stack() -> None:
    source = Path("her-core/her_mcp/manager.py").read_text()
    assert "except asyncio.CancelledError as exc" in source
    assert "await stack.aclose()" in source
    assert "raise" in source


def test_scheduler_uses_time_module_for_execution_timing() -> None:
    source = Path("her-core/utils/scheduler.py").read_text()
    assert "import time" in source
    assert "time.time()" in source


def test_scheduler_supports_runtime_updates_and_persistence() -> None:
    source = Path("her-core/utils/scheduler.py").read_text()
    assert "def persist_tasks" in source
    assert "def set_task_interval" in source
    assert "def set_task_enabled" in source
    assert "def run_task_now" in source
    assert "def is_valid_interval" in source
    assert 'task_type == "workflow"' in source
    assert "def _execute_workflow_task" in source
    assert "def _execute_workflow_step" in source
    assert 'if "when" in step' in source
    assert 'if action == "set_state"' in source
    assert "def _send_telegram_notification" in source
    assert 'task_type == "reminder"' in source
    assert "def get_upcoming_jobs" in source
    assert "her:scheduler:state" in source
    assert 'task.get("at"' in source
    assert '"once"' in source
    assert "max_retries" in source
    assert "retry_delay_seconds" in source
    assert "one_time" in source
    assert 'task_type == "self_optimization"' in source
    assert "weekly_self_optimization" in source
    assert "summarize_recent_patterns" in source
    assert "her:scheduler:tasks_override" in source
    assert "Loaded %s scheduler tasks from Redis override" in source
    assert "step skipped (when=undefined name)" in source
    assert "condition=false (undefined name)" in source
    assert "set failed: undefined name in expr" in source


def test_mcp_profile_path_is_configurable_via_env() -> None:
    main_source = Path("her-core/main.py").read_text()
    env_example = Path(".env.example").read_text()

    assert 'os.getenv("MCP_CONFIG_PATH", "mcp_servers.yaml")' in main_source
    assert "MCP_CONFIG_PATH=mcp_servers.yaml" in env_example
    assert "SANDBOX_CONTAINER_NAME=her-sandbox" in env_example
    assert "HER_CONFIG_DIR=" in env_example


def test_telegram_registers_schedule_admin_command() -> None:
    bot_source = Path("her-core/her_telegram/bot.py").read_text()
    handlers_source = Path("her-core/her_telegram/handlers.py").read_text()
    telegram_config = Path("config/telegram.yaml").read_text()

    assert 'CommandHandler("schedule", self.handlers.schedule_command)' in bot_source
    assert 'CommandHandler("example", self.handlers.example_command)' in bot_source
    assert "/schedule" in handlers_source
    assert "/example" in handlers_source
    assert "/schedule - Manage scheduled tasks" in telegram_config
    assert "/example - Show ready-to-use examples" in telegram_config
    assert "[key=value ...]" in handlers_source
    assert "task_type == \"workflow\"" in handlers_source
    assert "def _maybe_schedule_from_message" in handlers_source
    assert "def _parse_schedule_request" in handlers_source
    assert "def example_command" in handlers_source
    assert "_EXAMPLE_PROMPTS" in handlers_source
    assert "Got it. I'll remind you" in handlers_source
    assert "ReinforcementEngine" in handlers_source
    assert "Adaptive communication profile" in handlers_source
    assert "reinforcement_lesson" in handlers_source
    assert "if isinstance(text_value, list)" in handlers_source
    assert "_EVERY_INTERVAL_PATTERN" in handlers_source
    assert "_IN_INTERVAL_PATTERN" in handlers_source
    assert "def _interval_unit_to_base" in handlers_source
    assert "def _parse_schedule_request_with_llm" in handlers_source
    assert "Return strict JSON only" in handlers_source
    assert "reference only defined names" in handlers_source
    assert "def _wants_utc_timestamp" in handlers_source
    assert "def _maybe_answer_sandbox_security_query" in handlers_source
    assert "SandboxNetworkTool" in handlers_source
    assert "Port scan summary for" in handlers_source
    assert "Timestamp (UTC):" in handlers_source
    assert "wants_utc_stamp" in handlers_source
    assert "self._parse_schedule_request_with_llm(message, user_id)" in handlers_source


def test_reinforcement_engine_persists_scores_and_profiles() -> None:
    source = Path("her-core/utils/reinforcement.py").read_text()
    schema = Path("her-core/memory/schemas.sql").read_text()
    assert "class ReinforcementEngine" in source
    assert "def evaluate(" in source
    assert "her:reinforcement:events" in source
    assert "her:reinforcement:profile" in source
    assert "event_type=\"reinforcement_event\"" in source
    assert "CREATE TABLE IF NOT EXISTS reinforcement_events" in schema


def test_dashboard_handles_mem0_schema_and_recent_chats() -> None:
    source = Path("dashboard/app.py").read_text()
    assert "conn.autocommit = True" in source
    assert "payload->'metadata'->>'category'" in source
    assert 'scan_iter(match="her:context:*"' in source
    assert "her:scheduler:state" in source
    assert "her:decision:logs" in source
    assert "parse_execs_from_decisions" in source
    assert 'if str(payload.get("event_type", "")) != "sandbox_execution"' in source
    assert "Upcoming Jobs" in source
    assert "Behind The Chat: Reasoning / Tool Trace" in source
    assert "\"tool_call\"" in source
    assert "\"tool_result\"" in source


def test_timezone_is_configured_project_wide() -> None:
    compose_source = Path("docker-compose.yml").read_text()
    env_example = Path(".env.example").read_text()

    assert "TZ=UTC" in env_example
    assert "TZ: ${TZ:-UTC}" in compose_source
    assert "- TZ" in compose_source


def test_sandbox_security_and_network_tools_are_registered() -> None:
    sandbox_source = Path("her-core/her_mcp/sandbox_tools.py").read_text()
    tools_source = Path("her-core/her_mcp/tools.py").read_text()

    assert "class SandboxNetworkTool" in sandbox_source
    assert "class SandboxSecurityScanTool" in sandbox_source
    assert "event_type=\"sandbox_execution\"" in sandbox_source
    assert "Failed to write sandbox execution log to Redis" in sandbox_source
    assert "SandboxNetworkTool" in tools_source
    assert "SandboxSecurityScanTool" in tools_source


def test_sandbox_executor_uses_external_timeout_wrapper_not_docker_timeout_kwarg() -> None:
    sandbox_source = Path("her-core/her_mcp/sandbox_tools.py").read_text()
    assert "timeout --signal=TERM --kill-after=5s" in sandbox_source
    assert "self.container.exec_run(" in sandbox_source
    assert "wrapped," in sandbox_source
    assert "self.container.exec_run(\n                wrapped,\n                user=user,\n                workdir=workdir,\n                timeout=" not in sandbox_source


def test_handlers_route_messages_via_unified_interpreter_first() -> None:
    handlers_source = Path("her-core/her_telegram/handlers.py").read_text()
    interpreter_source = Path("her-core/her_telegram/unified_interpreter.py").read_text()
    assert "UnifiedRequestInterpreter" in handlers_source
    assert "self._maybe_handle_unified_request(message, user_id)" in handlers_source
    assert "SCHEDULE " in interpreter_source
    assert "SANDBOX " in interpreter_source
    assert "Detect language and understand non-English text." in interpreter_source


def test_sandbox_container_emits_startup_ready_log() -> None:
    source = Path("sandbox/Dockerfile").read_text()
    assert "[sandbox] Ready:" in source
    assert "tail -f /dev/null" in source
    assert "check_pentest_tools" in source


def test_sitecustomize_filters_known_pydantic_transition_warnings() -> None:
    source = Path("her-core/sitecustomize.py").read_text()
    assert "CrewAgentExecutor" in source
    assert "model_dump" in source
    assert r"langchain_openai\.chat_models\.base" in source


def test_runtime_capability_degradation_is_logged_and_published() -> None:
    main_source = Path("her-core/main.py").read_text()
    tools_source = Path("her-core/her_mcp/tools.py").read_text()
    dashboard_source = Path("dashboard/app.py").read_text()

    assert "_publish_runtime_capabilities" in main_source
    assert "her:runtime:capabilities" in main_source
    assert "_log_degraded_capabilities" in main_source
    assert "_probe_internet_access" in tools_source
    assert "self.capability_status" in tools_source
    assert "DecisionLogger" in tools_source
    assert "event_type=\"tool_call\"" in tools_source
    assert "event_type=\"tool_result\"" in tools_source
    assert "get_runtime_capabilities" in dashboard_source
    assert "Runtime Capability Snapshot" in dashboard_source


def test_mcp_profiles_avoid_legacy_transport_flags() -> None:
    for profile_path in ("config/mcp_servers.yaml", "config/mcp_servers.local.yaml"):
        profile = yaml.safe_load(Path(profile_path).read_text())
        for server in profile.get("servers", []):
            args = server.get("args", [])
            if server.get("command") != "npx":
                continue
            # Legacy "--transport stdio" breaks several modern MCP npm servers
            # by being interpreted as positional path/URL args.
            assert "--transport" not in args


def test_mcp_pdf_server_uses_stdio_mode_in_profiles() -> None:
    for profile_path in ("config/mcp_servers.yaml", "config/mcp_servers.local.yaml"):
        profile = yaml.safe_load(Path(profile_path).read_text())
        pdf_server = next(server for server in profile.get("servers", []) if server.get("name") == "pdf")
        assert "--stdio" in pdf_server.get("args", [])


def test_mcp_manager_reports_missing_env_placeholders_clearly() -> None:
    source = Path("her-core/her_mcp/manager.py").read_text()
    assert "_find_unresolved_placeholders" in source
    assert "missing required environment variable(s)" in source


def test_mcp_manager_startup_is_timeout_bounded_and_pdf_stdio_hardened() -> None:
    source = Path("her-core/her_mcp/manager.py").read_text()
    assert "MCP_SERVER_START_TIMEOUT_SECONDS" in source
    assert "asyncio.wait_for(" in source
    assert "_normalize_known_server_args" in source
    assert "and name == \"pdf\"" in source
    assert "normalized.append(\"--stdio\")" in source


def test_main_degrades_when_mcp_bootstrap_or_tool_wiring_fails() -> None:
    source = Path("her-core/main.py").read_text()
    assert "MCP bootstrap failed; continuing without MCP servers" in source
    assert "Tool integration failed; falling back to no-tool mode" in source
    assert "if mcp_manager is not None:" in source
    assert "await mcp_manager.stop_all_servers()" in source


def test_memory_degrades_to_fallback_when_backends_are_unavailable() -> None:
    main_source = Path("her-core/main.py").read_text()
    telegram_source = Path("her-core/telegram_bot.py").read_text()
    memory_init_source = Path("her-core/memory/__init__.py").read_text()
    redis_source = Path("her-core/memory/redis_client.py").read_text()

    assert "FallbackMemory" in main_source
    assert "degraded memory mode" in main_source
    assert "FallbackMemory" in telegram_source
    assert "FallbackMemory" in memory_init_source
    assert "_fallback_cache" in redis_source


def test_known_crewai_pydantic_mix_warning_is_suppressed() -> None:
    source = Path("her-core/sitecustomize.py").read_text()
    assert "warnings.filterwarnings(" in source
    assert "CrewAgentExecutor" in source
    assert "pydantic\\._internal\\._generate_schema" in source
