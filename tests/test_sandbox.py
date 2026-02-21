from pathlib import Path


def test_sandbox_has_docker_fallback_and_sanitized_native_execution() -> None:
    source = Path("her-core/her_mcp/sandbox_tools.py").read_text()

    assert "def docker_available" in source
    assert "def _execute_native(" in source
    assert "falling back to native execution" in source
    assert "❌ Command not available on server." in source
    assert "def _sanitize_error" in source

