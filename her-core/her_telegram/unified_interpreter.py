"""Unified LLM interpreter for natural-language task routing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from utils.schedule_helpers import extract_json_object


@dataclass
class InterpreterDecision:
    intent: str
    command: str
    confirmation: str
    language: str = "unknown"
    english: str = ""


class UnifiedRequestInterpreter:
    """Convert any user message to a strict command envelope."""

    def __init__(self, llm_invoke: Callable[[list[Any], int], tuple[str, bool]]):
        self._llm_invoke = llm_invoke

    def interpret(self, message: str, user_id: int, timezone_name: str = "UTC") -> InterpreterDecision | None:
        now_utc = datetime.now(UTC)
        prompt = (
            "Interpret this user message for an automation assistant.\n"
            f"Current UTC time: {now_utc.isoformat()}\n"
            f"Scheduler timezone default: {timezone_name}\n"
            "Execution mindset:\n"
            "- Convert user intent into an actionable objective.\n"
            "- Prefer direct executable outcomes over discussion.\n"
            "- If user text is ambiguous, infer the most likely practical intent.\n"
            "- Do not default to refusal framing; route to best supported command or NONE.\n"
            "Detect language and understand non-English text.\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "intent": "schedule|sandbox|none",\n'
            '  "language": "ISO-ish language code",\n'
            '  "english": "short English translation/normalization",\n'
            '  "confirmation": "short user-facing confirmation in English",\n'
            '  "command": "ONE exact command envelope"\n'
            "}\n"
            "Command envelope rules:\n"
            "- For scheduling requests, command MUST be: SCHEDULE {JSON task object}\n"
            "- For sandbox/network requests, command MUST be: SANDBOX <exact shell command>\n"
            "- For regular chat or unknown intent, command MUST be: NONE\n"
            "Scheduler task JSON fields:\n"
            "- name, type(reminder|workflow|custom), interval, run_at(optional), at(optional), timezone(optional), "
            "weekdays(optional), message(optional), notify_user_id(optional), max_retries(optional), retry_delay_seconds(optional), "
            "steps(optional), source_url(optional), condition_expr(optional).\n"
            "Allowed interval values: once|hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days.\n"
            "Sandbox command constraints:\n"
            "- Use simple single command lines; no shell chaining.\n"
            "- Prefer: dig, ping, traceroute, nmap, openssl s_client, curl, wget.\n"
            f"User message: {message}"
        )
        llm_messages = [
            SystemMessage(
                content=(
                    "You are a deterministic command planner. "
                    "Always return valid JSON object only, no markdown."
                )
            ),
            HumanMessage(content=prompt),
        ]
        response_text, _ = self._llm_invoke(llm_messages, user_id)
        payload = extract_json_object(response_text)
        if not payload:
            return None

        intent = str(payload.get("intent", "none")).strip().lower()
        command = str(payload.get("command", "NONE")).strip()
        confirmation = str(payload.get("confirmation", "")).strip() or "Done."
        language = str(payload.get("language", "unknown")).strip() or "unknown"
        english = str(payload.get("english", "")).strip()

        if intent not in {"schedule", "sandbox", "none"}:
            intent = "none"
            command = "NONE"
        if intent == "schedule" and not command.startswith("SCHEDULE "):
            return None
        if intent == "sandbox" and not command.startswith("SANDBOX "):
            return None
        if intent == "none":
            command = "NONE"

        return InterpreterDecision(
            intent=intent,
            command=command,
            confirmation=confirmation,
            language=language,
            english=english,
        )
