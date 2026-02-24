from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
from uuid import UUID


@dataclass
class ContextWindow:
    """Computed prompt/message window within a token budget."""

    system_prompt: str
    messages: List[Dict[str, str]]
    dropped_messages: int


class TokenBudgetManager:
    """Approximate token budget manager with per-session usage accounting."""

    def __init__(self, max_input_tokens: int = 1800) -> None:
        self._max_input_tokens = max_input_tokens
        self._session_totals: Dict[UUID, int] = {}

    def build_window(
        self,
        session_id: UUID,
        base_system_prompt: str,
        context_sections: List[str],
        messages: List[Dict[str, str]],
    ) -> ContextWindow:
        """Assemble system prompt and chat messages within configured budget."""

        system_prompt = self._compose_system_prompt(base_system_prompt, context_sections)
        system_tokens = estimate_tokens(system_prompt)
        budget_for_messages = max(100, self._max_input_tokens - system_tokens)

        kept_reversed: List[Dict[str, str]] = []
        used = 0
        for message in reversed(messages):
            message_tokens = estimate_tokens(message.get("content", "")) + 4
            if used + message_tokens > budget_for_messages:
                continue
            kept_reversed.append(message)
            used += message_tokens

        kept_messages = list(reversed(kept_reversed))
        dropped = max(0, len(messages) - len(kept_messages))
        self._session_totals[session_id] = self._session_totals.get(session_id, 0) + system_tokens + used

        return ContextWindow(system_prompt=system_prompt, messages=kept_messages, dropped_messages=dropped)

    def session_tokens(self, session_id: UUID) -> int:
        """Return approximate total input tokens consumed by a session."""

        return self._session_totals.get(session_id, 0)

    def _compose_system_prompt(self, base_system_prompt: str, context_sections: List[str]) -> str:
        sections = [base_system_prompt]
        for section in context_sections:
            if section.strip():
                sections.append(section.strip())

        prompt = "\n\n".join(sections)
        if estimate_tokens(prompt) <= self._max_input_tokens:
            return prompt

        while sections and estimate_tokens("\n\n".join(sections)) > self._max_input_tokens:
            sections.pop()
        return "\n\n".join(sections)


def estimate_tokens(text: str) -> int:
    """Approximate token count with conservative word-based heuristic."""

    words = len(text.split())
    return max(1, int(words * 1.35))
