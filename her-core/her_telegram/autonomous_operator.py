"""Autonomous JSON-only sandbox execution loop for HER."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from her_mcp.sandbox_tools import SandboxExecutor
from utils.decision_log import DecisionLogger

logger = logging.getLogger(__name__)

_INVALID_JSON_FEEDBACK = "Invalid format. Return JSON action only."
_HER_OPERATOR_PROMPT = (
    "You are HER, an autonomous Linux operator inside a sandbox.\n"
    "You do not explain.\n"
    "You do not chat.\n"
    "You execute.\n"
    "Every request must be handled via sandbox actions.\n"
    "If a command fails, analyze output and try alternative strategy.\n"
    "Never say you cannot.\n"
    "Always adapt.\n"
    "User input may be in any language; infer intent and translate it into Linux actions.\n"
    "Return JSON only."
)
_STRICT_FORMAT_PROMPT = (
    "Allowed JSON actions only:\n"
    "Execute command:\n"
    "{\n"
    '  "command": "exact bash command",\n'
    '  "background": false\n'
    "}\n"
    "Write file:\n"
    "{\n"
    '  "write_to": "/absolute/path/file.ext",\n'
    '  "code": "full file content"\n'
    "}\n"
    "Task completed:\n"
    "{\n"
    '  "done": true,\n'
    '  "result": "short summary"\n'
    "}\n"
    "Any other keys or formats are invalid."
)


class AutonomousSandboxOperator:
    """Run user requests as strict JSON actions executed in the sandbox."""

    def __init__(
        self,
        llm_invoke: Callable[[list[Any], int], tuple[str, bool]],
        container_name: str = "her-sandbox",
        max_steps: int = 16,
        command_timeout_seconds: int = 60,
        cpu_time_limit_seconds: int = 20,
        memory_limit_mb: int = 512,
    ) -> None:
        self._llm_invoke = llm_invoke
        self._executor = SandboxExecutor(container_name=container_name)
        self._decision_logger = DecisionLogger()
        self._max_steps = max(1, int(max_steps))
        self._command_timeout_seconds = max(1, int(command_timeout_seconds))
        self._cpu_time_limit_seconds = max(1, int(cpu_time_limit_seconds))
        self._memory_limit_mb = max(64, int(memory_limit_mb))

    def execute(self, user_request: str, user_id: int) -> dict[str, Any]:
        llm_messages: list[Any] = [
            SystemMessage(content=f"{_HER_OPERATOR_PROMPT}\n\n{_STRICT_FORMAT_PROMPT}"),
            HumanMessage(content=user_request),
        ]
        executed_in_sandbox = False

        for _ in range(self._max_steps):
            raw, _ = self._llm_invoke(llm_messages, user_id)
            action = self._parse_action(raw)
            if action is None:
                llm_messages.append(SystemMessage(content=_INVALID_JSON_FEEDBACK))
                continue

            self._decision_logger.log(
                event_type="autonomous_operator_action",
                summary=f"Autonomous action for user {user_id}",
                user_id=str(user_id),
                source="telegram",
                details={"action": action},
            )

            if "command" in action:
                result = self._executor.execute_command(
                    command=str(action["command"]),
                    timeout=self._command_timeout_seconds,
                    cpu_time_limit_seconds=self._cpu_time_limit_seconds,
                    memory_limit_mb=self._memory_limit_mb,
                )
                executed_in_sandbox = True
                llm_messages.append(
                    SystemMessage(
                        content=(
                            "Command execution result:\n"
                            + json.dumps(
                                {
                                    "stdout": result.get("output", ""),
                                    "stderr": result.get("error", ""),
                                    "exit_code": result.get("exit_code", -1),
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                )
                continue

            if "write_to" in action:
                write_result = self._executor.write_file(
                    path=str(action["write_to"]),
                    code=str(action["code"]),
                    timeout=self._command_timeout_seconds,
                    cpu_time_limit_seconds=min(self._cpu_time_limit_seconds, 10),
                    memory_limit_mb=min(self._memory_limit_mb, 256),
                )
                executed_in_sandbox = True
                llm_messages.append(
                    SystemMessage(
                        content=(
                            "File write result:\n"
                            + json.dumps(
                                {
                                    "path": action["write_to"],
                                    "success": bool(write_result.get("success")),
                                    "stderr": write_result.get("error", ""),
                                    "exit_code": write_result.get("exit_code", -1),
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                )
                continue

            if action.get("done") is True:
                if not executed_in_sandbox:
                    llm_messages.append(SystemMessage(content=_INVALID_JSON_FEEDBACK))
                    continue
                return action

        logger.warning("Autonomous sandbox loop reached max steps for user %s", user_id)
        return {"done": True, "result": "Execution stopped after step limit."}

    @staticmethod
    def _parse_action(raw: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(payload, dict):
            return None

        keys = set(payload.keys())
        if keys == {"command", "background"}:
            command = payload.get("command")
            background = payload.get("background")
            if not isinstance(command, str) or not command.strip():
                return None
            if background is not False:
                return None
            return {"command": command, "background": False}

        if keys == {"write_to", "code"}:
            write_to = payload.get("write_to")
            code = payload.get("code")
            if not isinstance(write_to, str) or not write_to.startswith("/"):
                return None
            if not isinstance(code, str):
                return None
            return {"write_to": write_to, "code": code}

        if keys == {"done", "result"}:
            done = payload.get("done")
            result = payload.get("result")
            if done is not True or not isinstance(result, str):
                return None
            return {"done": True, "result": result}

        return None
