from pathlib import Path


def test_schedule_mutation_and_direct_runtime_handlers_are_wired() -> None:
    source = Path("her-core/her_telegram/handlers.py").read_text()
    scheduler_source = Path("her-core/utils/scheduler.py").read_text()

    assert "def _maybe_apply_schedule_mutation" in source
    assert "def _maybe_handle_direct_runtime_request" in source
    assert "self._maybe_handle_direct_runtime_request(message=message, user_id=user_id)" in source
    assert "def remove_task(self, name: str) -> bool" in scheduler_source


def test_docker_runtime_integration_tests_exist() -> None:
    integration_source = Path("tests/integration/test_docker_runtime_e2e.py").read_text()
    docs_source = Path("docs/testing.md").read_text()

    assert "RUN_DOCKER_INTEGRATION=1" in integration_source
    assert "test_real_btc_workflow_polling_in_scheduler" in integration_source
    assert "test_real_nmap_execution_via_api" in integration_source
    assert "test_schedule_add_and_remove_via_user_messages" in integration_source
    assert "tests/integration/test_docker_runtime_e2e.py" in docs_source
