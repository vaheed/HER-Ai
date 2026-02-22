"""Autonomous JSON-only sandbox execution loop for HER."""

from __future__ import annotations

import json
import logging
import os
import re
import time
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
_ERROR_MARKERS = ("traceback", "exception", "error:", "command not available")


class AutonomousSandboxOperator:
    """Run user requests as strict JSON actions executed in the sandbox."""

    def __init__(
        self,
        llm_invoke: Callable[[list[Any], int], tuple[str, bool]],
        container_name: str = "her-sandbox",
        max_steps: int = 5,
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
        self._allowed_binaries = {
            "dig",
            "ping",
            "mtr",
            "traceroute",
            "nmap",
            "openssl",
            "curl",
            "wget",
            "python3",
            "node",
            "bash",
            "ls",
            "cat",
            "whois",
            "nslookup",
        }

    def execute(self, user_request: str, user_id: int) -> dict[str, Any]:
        return self.execute_with_history(
            user_request=user_request,
            user_id=user_id,
            conversation_history=[],
            language="unknown",
        )

    def execute_with_history(
        self,
        user_request: str,
        user_id: int,
        conversation_history: list[dict[str, Any]],
        language: str,
        on_step_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        history_lines: list[str] = []
        for item in conversation_history:
            role = str(item.get("role", "user"))
            msg = str(item.get("message", ""))
            if msg.strip():
                history_lines.append(f"{role}: {msg}")
        history_text = "\n".join(history_lines) if history_lines else "(none)"
        llm_messages: list[Any] = [
            SystemMessage(
                content=(
                    f"{_HER_OPERATOR_PROMPT}\n\n{_STRICT_FORMAT_PROMPT}\n\n"
                    "Response language rules:\n"
                    f"- Latest user language: {language}\n"
                    "- Any user-visible text in JSON fields must match that language.\n"
                )
            ),
            HumanMessage(
                content=(
                    "Full conversation history (oldest to newest):\n"
                    f"{history_text}\n\n"
                    f"Latest user request:\n{user_request}"
                )
            ),
        ]
        executed_in_sandbox = False
        seen_commands: set[str] = set()
        steps = 0

        while steps < min(self._max_steps, 5):
            steps += 1
            step_started = time.perf_counter()
            raw, _ = self._llm_invoke(llm_messages, user_id)
            action = self._parse_action(raw)
            if action is None:
                llm_messages.append(SystemMessage(content=_INVALID_JSON_FEEDBACK))
                continue
            if on_step_event:
                on_step_event(
                    {
                        "event": "step_start",
                        "step_number": steps,
                        "action": "command" if "command" in action else ("write" if "write_to" in action else "analysis"),
                    }
                )

            logger.info(
                {
                    "event": "agent_step",
                    "step": steps,
                    "action": "command" if "command" in action else ("analysis" if "done" not in action else "synthesize"),
                    "command": action.get("command"),
                }
            )
            self._decision_logger.log(
                event_type="agent_step",
                summary=f"Agent step {steps} for user {user_id}",
                user_id=str(user_id),
                source="telegram",
                details={"step": steps, "action": action},
            )

            if "command" in action:
                command = str(action["command"]).strip()
                if not self._validate_command(command):
                    llm_messages.append(
                        SystemMessage(content="Command rejected by safety policy. Use one safe command without chaining.")
                    )
                    continue
                if command in seen_commands:
                    return {"done": True, "result": "Execution stopped due to repeated identical command."}
                seen_commands.add(command)
                result = self._executor.execute_command(
                    command=command,
                    timeout=self._command_timeout_seconds,
                    cpu_time_limit_seconds=self._cpu_time_limit_seconds,
                    memory_limit_mb=self._memory_limit_mb,
                )
                executed_in_sandbox = True
                verified = self._verify_step(user_request=user_request, command=command, result=result)
                if on_step_event:
                    on_step_event(
                        {
                            "event": "step_complete",
                            "step_number": steps,
                            "action": "command",
                            "output_preview": str(result.get("output", ""))[:180],
                            "verified": verified,
                            "execution_ms": round((time.perf_counter() - step_started) * 1000.0, 2),
                        }
                    )
                llm_messages.append(
                    SystemMessage(
                        content=(
                            "Command execution result:\n"
                            + json.dumps(
                                {
                                    "stdout": str(result.get("output", ""))[:2500],
                                    "stderr": str(result.get("error", ""))[:1200],
                                    "exit_code": result.get("exit_code", -1),
                                    "verified": verified,
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                )
                if not verified:
                    llm_messages.append(
                        SystemMessage(
                            content=(
                                "Verification failed. Output must be non-empty, relevant to the request, and error-free. "
                                "Adapt command strategy."
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
                if on_step_event:
                    on_step_event(
                        {
                            "event": "step_complete",
                            "step_number": steps,
                            "action": "write",
                            "output_preview": str(write_result.get("error", "") or "write_ok")[:180],
                            "verified": bool(write_result.get("success")),
                            "execution_ms": round((time.perf_counter() - step_started) * 1000.0, 2),
                        }
                    )
                continue

            if action.get("done") is True:
                if not executed_in_sandbox or self.requires_tool(user_request):
                    llm_messages.append(SystemMessage(content=_INVALID_JSON_FEEDBACK))
                    continue
                if on_step_event:
                    on_step_event(
                        {
                            "event": "step_complete",
                            "step_number": steps,
                            "action": "synthesize",
                            "output_preview": str(action.get("result", ""))[:180],
                            "verified": True,
                            "execution_ms": round((time.perf_counter() - step_started) * 1000.0, 2),
                        }
                    )
                return action

        logger.warning("Autonomous sandbox loop reached max steps for user %s", user_id)
        return {"done": True, "result": "Execution stopped after step limit."}

    @staticmethod
    def requires_tool(question: str) -> bool:
        lower = str(question or "").lower()
        keywords = {
            "math",
            "time",
            "search",
            "fetch",
            "compute",
            "system",
            "file",
            "data",
            "run",
            "execute",
            "check",
            "scan",
            "price",
            "latest",
        }
        return any(token in lower for token in keywords)

    def _validate_command(self, command: str) -> bool:
        stripped = command.strip()
        if not stripped:
            return False
        if any(token in stripped for token in (";", "&&", "||", "|", "`", "$(")):
            return False
        binary = stripped.split(" ", 1)[0].strip()
        if binary not in self._allowed_binaries:
            return False
        return True

    @staticmethod
    def _verify_step(user_request: str, command: str, result: dict[str, Any]) -> bool:
        output = str(result.get("output", "") or "").strip()
        error = str(result.get("error", "") or "").strip().lower()
        if bool(result.get("success")) and output:
            pass
        elif output:
            pass
        else:
            return False
        if any(marker in error for marker in _ERROR_MARKERS):
            return False
        request_tokens = {token for token in re.findall(r"[a-z0-9]{3,}", user_request.lower())}
        command_tokens = {token for token in re.findall(r"[a-z0-9]{3,}", command.lower())}
        relevance = len(request_tokens.intersection(command_tokens)) > 0
        return relevance or bool(result.get("success"))

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
