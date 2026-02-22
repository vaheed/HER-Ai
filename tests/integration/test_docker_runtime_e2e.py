from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _integration_enabled() -> bool:
    return os.getenv("RUN_DOCKER_INTEGRATION", "").strip().lower() in {"1", "true", "yes", "on"}


def _run_compose(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    compose_files = [
        item.strip()
        for item in os.getenv("HER_E2E_COMPOSE_FILES", "docker-compose.yml").split(":")
        if item.strip()
    ]
    cmd = ["docker", "compose"]
    for compose_file in compose_files:
        cmd.extend(["-f", compose_file])
    cmd.extend(args)
    return subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


def _wait_for_http(url: str, timeout_seconds: int = 180) -> None:
    deadline = time.time() + timeout_seconds
    last_err = ""
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for {url}. Last error: {last_err}")


def _api_chat(message: str, user_id: int, chat_id: int | None = None) -> dict:
    payload = {"user_id": user_id, "message": message}
    if chat_id is not None:
        payload["chat_id"] = chat_id
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url="http://localhost:8082/api/v1/chat",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def _docker_exec_python(service: str, code: str, timeout: int = 180) -> dict:
    result = _run_compose(
        ["exec", "-T", service, "python", "-c", code],
        timeout=timeout,
    )
    stdout = result.stdout.strip()
    if not stdout:
        raise AssertionError(f"No output from docker compose exec {service}. stderr={result.stderr}")
    return json.loads(stdout.splitlines()[-1])


@pytest.fixture(scope="module")
def docker_runtime_stack() -> None:
    if not _integration_enabled():
        pytest.skip("Set RUN_DOCKER_INTEGRATION=1 to run Docker runtime integration tests.")
    if not _docker_available():
        pytest.skip("Docker CLI is not available on this machine.")

    autostart = os.getenv("HER_E2E_AUTOSTART_STACK", "false").strip().lower() in {"1", "true", "yes", "on"}
    keep_stack = os.getenv("HER_E2E_KEEP_STACK", "true").strip().lower() in {"1", "true", "yes", "on"}
    services = [item.strip() for item in os.getenv("HER_E2E_SERVICES", "").split() if item.strip()]

    if autostart:
        up_args = ["up", "-d", "--build", *services] if services else ["up", "-d", "--build"]
        _run_compose(up_args, timeout=1800)

    _wait_for_http("http://localhost:8000", timeout_seconds=300)
    _wait_for_http("http://localhost:8082/api/health", timeout_seconds=300)

    yield

    if autostart and not keep_stack:
        _run_compose(["down", "-v"], timeout=300)


def test_real_btc_workflow_polling_in_scheduler(docker_runtime_stack: None) -> None:
    code = r"""
import asyncio
import json

from utils.scheduler import get_scheduler

TASK_NAME = "e2e_btc_runtime_poll"

async def main():
    scheduler = get_scheduler()
    await scheduler.start()
    scheduler.remove_task(TASK_NAME)
    scheduler.add_task(
        name=TASK_NAME,
        interval="every_5_minutes",
        task_type="workflow",
        enabled=True,
        source_url="https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
        steps=[
            {"action": "set", "key": "price", "expr": "float(source['bitcoin']['usd'])"},
            {"action": "set_state", "key": "last_price", "expr": "price"},
        ],
        notify_user_id=1,
        max_retries=2,
        retry_delay_seconds=10,
    )
    ok, details = await scheduler.run_task_now(TASK_NAME)
    task = None
    for row in scheduler.get_tasks():
        if str(row.get("name")) == TASK_NAME:
            task = row
            break
    state = (task or {}).get("_state", {})
    price = state.get("last_price")
    scheduler.remove_task(TASK_NAME)
    scheduler.persist_tasks()
    await scheduler.stop()
    print(json.dumps({"ok": ok, "details": details, "price": price}))

asyncio.run(main())
"""
    result = _docker_exec_python("her-bot", code, timeout=240)
    assert bool(result.get("ok")) is True
    assert float(result.get("price") or 0.0) > 0.0


def test_real_nmap_execution_via_api(docker_runtime_stack: None) -> None:
    response = _api_chat(
        user_id=9021001,
        chat_id=9021001,
        message="Please run a port scan (nmap) for scanme.nmap.org and summarize open ports.",
    )
    text = str(response.get("response", ""))
    assert "Port scan summary for scanme.nmap.org" in text
    assert "Sandbox security tools are currently unavailable" not in text
    assert "Command not available on server" not in text


def test_schedule_add_and_remove_via_user_messages(docker_runtime_stack: None) -> None:
    user_id = 9021002
    chat_id = 9021002

    inspect_code = rf"""
import json
from utils.scheduler import get_scheduler

scheduler = get_scheduler()
tasks = [t for t in scheduler.get_tasks() if str(t.get("notify_user_id", "")) == "{user_id}"]
print(json.dumps({{"count": len(tasks), "names": [str(t.get("name", "")) for t in tasks]}}))
"""
    before = _docker_exec_python("her-bot", inspect_code)
    before_names = set(before.get("names", []))

    created = _api_chat(
        user_id=user_id,
        chat_id=chat_id,
        message="Remind me every 5 minutes to review BTC movement and risk.",
    )
    assert int(created.get("scheduled_tasks", 0)) >= 1

    after_create = _docker_exec_python("her-bot", inspect_code)
    after_names = set(after_create.get("names", []))
    new_names = sorted(after_names - before_names)
    assert new_names, f"No new tasks created. Response={created}"

    task_to_remove = new_names[0]
    removed = _api_chat(
        user_id=user_id,
        chat_id=chat_id,
        message=f"remove task {task_to_remove}",
    )
    assert f"`{task_to_remove}`" in str(removed.get("response", ""))

    after_remove = _docker_exec_python("her-bot", inspect_code)
    assert task_to_remove not in set(after_remove.get("names", []))
