"""Sandbox execution tools for online operations, testing, and reporting.

All execution happens in the isolated 'her-sandbox' Docker container via docker exec.
The sandbox container is configured with:
- Container name: 'her-sandbox' (configurable via SANDBOX_CONTAINER_NAME env var)
- User: 'sandbox' (non-root, isolated)
- Workspace: /workspace (persistent volume)
- Temp: /tmp (tmpfs, noexec)
- Network: her-network (isolated from host)
- Read-only filesystem (except /workspace and /tmp)
"""

import json
import logging
import os
import time
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class SandboxExecutor:
    """Execute commands in the sandbox container via Docker.
    
    All commands are executed using docker exec in the 'her-sandbox' container.
    This ensures complete isolation from the host system and other containers.
    """

    def __init__(self, container_name: str = "her-sandbox"):
        self.container_name = container_name
        self._client = None
        self._container = None

    @property
    def client(self):
        """Lazy-load Docker client."""
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except ImportError:
                logger.error("docker package not installed. Install with: pip install docker")
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to connect to Docker: %s", exc)
                raise
        return self._client

    @property
    def container(self):
        """Lazy-load container reference."""
        if self._container is None:
            try:
                self._container = self.client.containers.get(self.container_name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to get container '%s': %s", self.container_name, exc)
                raise
        return self._container

    def execute_command(
        self,
        command: str,
        timeout: int = 30,
        workdir: str = "/workspace",
        user: str = "sandbox",
    ) -> dict[str, Any]:
        """
        Execute a command in the sandbox container.

        Args:
            command: Command to execute
            timeout: Execution timeout in seconds
            workdir: Working directory (default: /workspace)
            user: User to run as (default: sandbox)

        Returns:
            Dict with success, output, error, exit_code, execution_time
        """
        start_time = time.time()
        try:
            result = self.container.exec_run(
                command,
                user=user,
                workdir=workdir,
                timeout=timeout,
                demux=True,  # Returns (stdout, stderr) tuple
            )
            execution_time = time.time() - start_time

            stdout, stderr = result.output
            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            result_dict = {
                "success": result.exit_code == 0,
                "output": stdout_str,
                "error": stderr_str,
                "exit_code": result.exit_code,
                "execution_time": execution_time,
            }
            # Log to Redis if metrics available
            self._log_execution(command, result_dict, user, workdir)
            return result_dict
        except Exception as exc:  # noqa: BLE001
            execution_time = time.time() - start_time
            result_dict = {
                "success": False,
                "output": "",
                "error": str(exc),
                "exit_code": -1,
                "execution_time": execution_time,
            }
            self._log_execution(command, result_dict, user, workdir)
            return result_dict

    def _log_execution(self, command: str, result: dict[str, Any], user: str, workdir: str):
        """Log execution to Redis metrics if available."""
        try:
            import redis
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_password = os.getenv("REDIS_PASSWORD", "")

            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
            )

            import json
            from datetime import datetime, timezone

            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "command": command,
                "success": result["success"],
                "output": result.get("output", ""),
                "error": result.get("error", ""),
                "exit_code": result.get("exit_code", -1),
                "execution_time": result.get("execution_time", 0),
                "user": user,
                "workdir": workdir,
            }

            redis_client.lpush("her:sandbox:executions", json.dumps(payload))
            redis_client.ltrim("her:sandbox:executions", 0, 99)
        except Exception:  # noqa: BLE001
            # Silently fail if Redis not available
            pass

    def execute_python(
        self,
        code: str,
        timeout: int = 30,
        workdir: str = "/workspace",
    ) -> dict[str, Any]:
        """
        Execute Python code in the sandbox.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            workdir: Working directory

        Returns:
            Dict with execution results
        """
        # Write code to temporary file
        script_name = f"script_{int(time.time())}.py"
        script_path = f"/tmp/{script_name}"

        # Write script
        write_result = self.execute_command(
            f"bash -c 'cat > {script_path} << \"PYEOF\"\n{code}\nPYEOF'",
            timeout=10,
        )
        if not write_result["success"]:
            return {
                "success": False,
                "output": "",
                "error": f"Failed to write script: {write_result['error']}",
                "exit_code": -1,
                "execution_time": 0,
            }

        try:
            # Execute script
            result = self.execute_command(
                f"python3 {script_path}",
                timeout=timeout,
                workdir=workdir,
            )
            return result
        finally:
            # Cleanup
            self.execute_command(f"rm -f {script_path}", timeout=5)

    def execute_shell(
        self,
        script: str,
        timeout: int = 30,
        workdir: str = "/workspace",
    ) -> dict[str, Any]:
        """
        Execute shell script in the sandbox.

        Args:
            script: Shell script to execute
            timeout: Execution timeout in seconds
            workdir: Working directory

        Returns:
            Dict with execution results
        """
        script_name = f"script_{int(time.time())}.sh"
        script_path = f"/tmp/{script_name}"

        # Write script
        write_result = self.execute_command(
            f"bash -c 'cat > {script_path} << \"SHEOF\"\n{script}\nSHEOF'",
            timeout=10,
        )
        if not write_result["success"]:
            return {
                "success": False,
                "output": "",
                "error": f"Failed to write script: {write_result['error']}",
                "exit_code": -1,
                "execution_time": 0,
            }

        try:
            # Make executable and run
            self.execute_command(f"chmod +x {script_path}", timeout=5)
            result = self.execute_command(
                f"bash {script_path}",
                timeout=timeout,
                workdir=workdir,
            )
            return result
        finally:
            # Cleanup
            self.execute_command(f"rm -f {script_path}", timeout=5)


class SandboxCommandTool(BaseTool):
    """Execute arbitrary commands in the sandbox container."""

    name: str = "sandbox_execute"
    description: str = (
        "Execute a command in the sandbox container. "
        "Useful for running curl, wget, python, node, or any shell command. "
        "Returns stdout, stderr, exit code, and execution time."
    )

    def __init__(self, container_name: str = "her-sandbox", **kwargs: Any):
        super().__init__(**kwargs)
        self.executor = SandboxExecutor(container_name)

    def _run(
        self,
        command: str,
        timeout: int = 30,
        workdir: str = "/workspace",
        **_: Any,
    ) -> str:
        """Execute command in sandbox."""
        if not command.strip():
            return "Error: Empty command"

        result = self.executor.execute_command(command, timeout=int(timeout), workdir=workdir)

        response_parts = []
        if result["success"]:
            response_parts.append("✅ Command executed successfully")
        else:
            response_parts.append(f"❌ Command failed (exit code: {result['exit_code']})")

        if result["output"]:
            response_parts.append(f"\n📤 Output:\n{result['output']}")

        if result["error"]:
            response_parts.append(f"\n⚠️  Errors:\n{result['error']}")

        response_parts.append(f"\n⏱️  Execution time: {result['execution_time']:.2f}s")

        return "\n".join(response_parts)


class SandboxPythonTool(BaseTool):
    """Execute Python code in the sandbox container."""

    name: str = "sandbox_python"
    description: str = (
        "Execute Python code in the sandbox container. "
        "Useful for data processing, API calls, testing, and analysis. "
        "Code runs in isolated sandbox environment."
    )

    def __init__(self, container_name: str = "her-sandbox", **kwargs: Any):
        super().__init__(**kwargs)
        self.executor = SandboxExecutor(container_name)

    def _run(
        self,
        code: str,
        timeout: int = 30,
        workdir: str = "/workspace",
        **_: Any,
    ) -> str:
        """Execute Python code in sandbox."""
        if not code.strip():
            return "Error: Empty code"

        result = self.executor.execute_python(code, timeout=int(timeout), workdir=workdir)

        response_parts = []
        if result["success"]:
            response_parts.append("✅ Python code executed successfully")
        else:
            response_parts.append(f"❌ Python execution failed (exit code: {result['exit_code']})")

        if result["output"]:
            response_parts.append(f"\n📤 Output:\n{result['output']}")

        if result["error"]:
            response_parts.append(f"\n⚠️  Errors:\n{result['error']}")

        response_parts.append(f"\n⏱️  Execution time: {result['execution_time']:.2f}s")

        return "\n".join(response_parts)


class SandboxWebTool(BaseTool):
    """Perform web operations (curl, wget, fetch) in the sandbox."""

    name: str = "sandbox_web"
    description: str = (
        "Perform web operations in the sandbox container using curl or wget. "
        "Useful for fetching URLs, testing APIs, downloading files, and web scraping. "
        "Returns response content, headers, and status codes."
    )

    def __init__(self, container_name: str = "her-sandbox", **kwargs: Any):
        super().__init__(**kwargs)
        self.executor = SandboxExecutor(container_name)

    def _run(
        self,
        url: str,
        method: str = "GET",
        headers: str = "",
        data: str = "",
        timeout: int = 30,
        **_: Any,
    ) -> str:
        """Fetch URL using curl in sandbox."""
        if not url.strip():
            return "Error: Empty URL"

        # Build curl command
        cmd_parts = ["curl", "-fsSL", "-w", "\\n%{http_code}", "-X", method.upper()]

        if headers:
            # Parse headers (format: "Header1: value1\\nHeader2: value2")
            for header_line in headers.split("\\n"):
                if ":" in header_line:
                    cmd_parts.extend(["-H", header_line.strip()])

        if data and method.upper() in ("POST", "PUT", "PATCH"):
            cmd_parts.extend(["-d", data])

        cmd_parts.extend(["--max-time", str(timeout), url])

        command = " ".join(f'"{part}"' if " " in part else part for part in cmd_parts)

        result = self.executor.execute_command(command, timeout=int(timeout) + 5)

        response_parts = []
        if result["success"]:
            response_parts.append("✅ Web request completed")
        else:
            response_parts.append(f"❌ Web request failed (exit code: {result['exit_code']})")

        if result["output"]:
            # Try to extract HTTP status code (last line)
            output_lines = result["output"].strip().split("\n")
            if output_lines and output_lines[-1].isdigit():
                status_code = output_lines[-1]
                content = "\n".join(output_lines[:-1])
                response_parts.append(f"\n📊 HTTP Status: {status_code}")
                if content:
                    response_parts.append(f"\n📤 Response:\n{content}")
            else:
                response_parts.append(f"\n📤 Response:\n{result['output']}")

        if result["error"]:
            response_parts.append(f"\n⚠️  Errors:\n{result['error']}")

        response_parts.append(f"\n⏱️  Execution time: {result['execution_time']:.2f}s")

        return "\n".join(response_parts)


class SandboxTestTool(BaseTool):
    """Run tests and generate reports in the sandbox."""

    name: str = "sandbox_test"
    description: str = (
        "Run tests and generate reports in the sandbox container. "
        "Supports pytest, unittest, custom test scripts, and reporting. "
        "Returns test results, coverage, and execution metrics."
    )

    def __init__(self, container_name: str = "her-sandbox", **kwargs: Any):
        super().__init__(**kwargs)
        self.executor = SandboxExecutor(container_name)

    def _run(
        self,
        test_command: str = "",
        test_file: str = "",
        test_type: str = "pytest",
        timeout: int = 60,
        **_: Any,
    ) -> str:
        """Run tests in sandbox."""
        if not test_command and not test_file:
            return "Error: Provide either test_command or test_file"

        if test_command:
            command = test_command
        elif test_type == "pytest":
            command = f"python3 -m pytest {test_file} -v"
        elif test_type == "unittest":
            command = f"python3 -m unittest {test_file}"
        else:
            command = f"python3 {test_file}"

        result = self.executor.execute_command(command, timeout=int(timeout))

        response_parts = []
        if result["success"]:
            response_parts.append("✅ Tests completed successfully")
        else:
            response_parts.append(f"❌ Tests failed (exit code: {result['exit_code']})")

        if result["output"]:
            response_parts.append(f"\n📊 Test Results:\n{result['output']}")

        if result["error"]:
            response_parts.append(f"\n⚠️  Test Errors:\n{result['error']}")

        response_parts.append(f"\n⏱️  Execution time: {result['execution_time']:.2f}s")

        return "\n".join(response_parts)


class SandboxReportTool(BaseTool):
    """Generate reports and summaries in the sandbox."""

    name: str = "sandbox_report"
    description: str = (
        "Generate reports, summaries, and analysis in the sandbox container. "
        "Can process data, create markdown reports, generate JSON summaries, "
        "and perform data analysis. Returns formatted report content."
    )

    def __init__(self, container_name: str = "her-sandbox", **kwargs: Any):
        super().__init__(**kwargs)
        self.executor = SandboxExecutor(container_name)

    def _run(
        self,
        report_script: str = "",
        data_file: str = "",
        report_format: str = "markdown",
        **_: Any,
    ) -> str:
        """Generate report in sandbox."""
        if not report_script and not data_file:
            return "Error: Provide report_script or data_file"

        if report_script:
            # Execute custom report script
            result = self.executor.execute_shell(report_script)
        else:
            # Generate basic report from data file
            python_code = f"""
import json
import sys
from pathlib import Path

data_file = Path("{data_file}")
if not data_file.exists():
    print(f"Error: File {{data_file}} not found", file=sys.stderr)
    sys.exit(1)

# Read and analyze data
try:
    with open(data_file) as f:
        if data_file.suffix == '.json':
            data = json.load(f)
        else:
            data = f.read()
    
    # Generate report
    print("# Report")
    print(f"\\n## Data File: {data_file}")
    print(f"\\n## Summary")
    if isinstance(data, dict):
        print(f"- Keys: {{len(data)}}")
        print(f"- Sample: {{str(data)[:200]}}")
    elif isinstance(data, list):
        print(f"- Items: {{len(data)}}")
        print(f"- Sample: {{str(data[:3])}}")
    else:
        print(f"- Length: {{len(str(data))}}")
        print(f"- Preview: {{str(data)[:500]}}")
except Exception as e:
    print(f"Error processing data: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
            result = self.executor.execute_python(python_code)

        response_parts = []
        if result["success"]:
            response_parts.append("✅ Report generated successfully")
        else:
            response_parts.append(f"❌ Report generation failed (exit code: {result['exit_code']})")

        if result["output"]:
            response_parts.append(f"\n📄 Report:\n{result['output']}")

        if result["error"]:
            response_parts.append(f"\n⚠️  Errors:\n{result['error']}")

        response_parts.append(f"\n⏱️  Execution time: {result['execution_time']:.2f}s")

        return "\n".join(response_parts)


class SandboxNetworkTool(BaseTool):
    """Run network diagnostics in the sandbox container."""

    name: str = "sandbox_network"
    description: str = (
        "Run network diagnostics in the sandbox container. "
        "Supports DNS lookup, ping, traceroute, port scan (nmap), and SSL checks."
    )

    def __init__(self, container_name: str = "her-sandbox", **kwargs: Any):
        super().__init__(**kwargs)
        self.executor = SandboxExecutor(container_name)

    def _run(
        self,
        target: str,
        action: str = "dns",
        ports: str = "1-1024",
        timeout: int = 45,
        **_: Any,
    ) -> str:
        """Run diagnostic commands in sandbox."""
        if not target.strip():
            return "Error: Empty target"

        normalized_action = action.strip().lower()
        if normalized_action == "dns":
            command = f"dig +short {target}"
        elif normalized_action == "ping":
            command = f"ping -c 4 {target}"
        elif normalized_action == "traceroute":
            command = f"traceroute -m 15 {target}"
        elif normalized_action == "port_scan":
            command = f"nmap -Pn -T4 -p {ports} {target}"
        elif normalized_action == "ssl":
            command = f"echo | openssl s_client -connect {target}:443 -servername {target}"
        else:
            return "Error: Unsupported action. Use dns, ping, traceroute, port_scan, or ssl."

        result = self.executor.execute_command(command, timeout=int(timeout))

        response_parts = []
        if result["success"]:
            response_parts.append("✅ Network diagnostic completed")
        else:
            response_parts.append(f"❌ Network diagnostic failed (exit code: {result['exit_code']})")

        if result["output"]:
            response_parts.append(f"\n📤 Output:\n{result['output']}")
        if result["error"]:
            response_parts.append(f"\n⚠️  Errors:\n{result['error']}")
        response_parts.append(f"\n⏱️  Execution time: {result['execution_time']:.2f}s")
        return "\n".join(response_parts)


class SandboxSecurityScanTool(BaseTool):
    """Run non-authenticated website and host security checks."""

    name: str = "sandbox_security_scan"
    description: str = (
        "Run baseline security checks (no API key) for hosts/websites: "
        "HTTP headers, robots.txt, TLS info, and common-port scans via nmap."
    )

    def __init__(self, container_name: str = "her-sandbox", **kwargs: Any):
        super().__init__(**kwargs)
        self.executor = SandboxExecutor(container_name)

    def _run(
        self,
        target: str,
        mode: str = "website",
        timeout: int = 90,
        **_: Any,
    ) -> str:
        if not target.strip():
            return "Error: Empty target"

        normalized_mode = mode.strip().lower()
        if normalized_mode == "website":
            script = f"""
set -e
echo "== HTTP HEADERS =="
curl -fsSIL --max-time 20 "{target}" || true
echo ""
echo "== ROBOTS.TXT =="
curl -fsSL --max-time 20 "{target.rstrip('/')}/robots.txt" || true
"""
        elif normalized_mode == "host":
            script = f"""
set -e
echo "== NMAP TOP PORTS =="
nmap -Pn -T4 --top-ports 200 "{target}" || true
echo ""
echo "== TLS HANDSHAKE =="
echo | openssl s_client -connect "{target}:443" -servername "{target}" 2>/dev/null | head -n 40 || true
"""
        else:
            return "Error: Unsupported mode. Use website or host."

        result = self.executor.execute_shell(script, timeout=int(timeout))

        response_parts = []
        if result["success"]:
            response_parts.append("✅ Security scan completed")
        else:
            response_parts.append(f"❌ Security scan failed (exit code: {result['exit_code']})")

        if result["output"]:
            response_parts.append(f"\n📤 Findings:\n{result['output']}")
        if result["error"]:
            response_parts.append(f"\n⚠️  Errors:\n{result['error']}")
        response_parts.append(f"\n⏱️  Execution time: {result['execution_time']:.2f}s")
        return "\n".join(response_parts)
