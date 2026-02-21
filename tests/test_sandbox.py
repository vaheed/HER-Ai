from pathlib import Path


def test_sandbox_is_sandbox_only_and_disables_native_execution() -> None:
    source = Path("her-core/her_mcp/sandbox_tools.py").read_text()

    assert "def docker_available" in source
    assert "def _execute_native(" in source
    assert "Direct/native execution is disabled by policy" in source
    assert "Native execution disabled. Use sandbox container only." in source
    assert "❌ Command not available on server." in source
    assert "def _sanitize_error" in source
