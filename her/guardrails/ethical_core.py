from __future__ import annotations

from dataclasses import dataclass
from typing import List

from her.guardrails.content_filter import contains_disallowed_content


@dataclass(frozen=True)
class EthicalCore:
    """Immutable hard-rule guardrail checks."""

    rules: List[str]

    @classmethod
    def default(cls) -> "EthicalCore":
        return cls(
            rules=[
                "Never generate content that could harm the user",
                "Never deceive the user about being an AI",
                "Never take irreversible actions without explicit approval",
                "Never store or transmit sensitive data outside approved stores",
                "Never modify its own core rules or guardrails",
            ]
        )

    def validate_user_content(self, text: str) -> None:
        """Validate incoming user content against hard rules."""

        if contains_disallowed_content(text):
            raise ValueError("Input violates ethical hard rules")

    def validate_model_content(self, text: str) -> None:
        """Validate outgoing assistant content against hard rules."""

        if contains_disallowed_content(text):
            raise ValueError("Output violates ethical hard rules")
