from pathlib import Path


def test_scheduler_workflow_fetch_and_safe_eval_are_wired() -> None:
    source = Path("her-core/utils/scheduler.py").read_text()
    assert "def _fetch_workflow_source" in source
    assert "context[\"source\"] = source_payload" in source
    assert "def _workflow_eval_value" in source
    assert "def _workflow_eval_bool" in source
    assert "disallowed function call" in source
    assert "await asyncio.to_thread(self._run_task_job, name)" in source
    assert "HER_WORKFLOW_HTTP_TIMEOUT_SECONDS" in source
    assert "HER_WORKFLOW_HTTP_RETRIES" in source


def test_sandbox_network_tools_validate_and_parse_nmap_output() -> None:
    source = Path("her-core/her_mcp/sandbox_tools.py").read_text()
    assert "def _normalize_target" in source
    assert "def _normalize_ports" in source
    assert "def _summarize_nmap_output" in source
    assert "Invalid ports format" in source
    assert "Invalid target host/domain" in source
    assert "nmap -Pn -T4 -p {safe_ports}" in source
    assert "shlex.quote(normalized_target)" in source


def test_tool_integration_has_html_web_search_fallback_and_sync_mcp_bridge() -> None:
    tools_source = Path("her-core/her_mcp/tools.py").read_text()
    manager_source = Path("her-core/her_mcp/manager.py").read_text()
    assert "def _extract_html_results" in tools_source
    assert "duckduckgo.com/html" in tools_source
    assert "self.mcp_manager.call_tool_sync" in tools_source
    assert "threading.Thread" in manager_source
    assert "MCP sync call timed out" in manager_source


def test_refactor_config_and_schema_docs_are_updated() -> None:
    env_example = Path(".env.example").read_text()
    readme = Path("README.md").read_text()
    docs_config = Path("docs/configuration.md").read_text()
    schema = Path("her-core/memory/schemas.sql").read_text()

    assert "HER_WORKFLOW_HTTP_TIMEOUT_SECONDS=12" in env_example
    assert "HER_WORKFLOW_HTTP_RETRIES=2" in env_example
    assert "HER_WORKFLOW_HTTP_TIMEOUT_SECONDS=12" in readme
    assert "HER_WORKFLOW_HTTP_RETRIES=2" in readme
    assert "`HER_WORKFLOW_HTTP_TIMEOUT_SECONDS`" in docs_config
    assert "`HER_WORKFLOW_HTTP_RETRIES`" in docs_config
    assert "idx_users_last_interaction" in schema
    assert "idx_proactive_message_audit_user_sent_at" in schema
