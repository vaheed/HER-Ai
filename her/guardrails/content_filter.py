from __future__ import annotations

from typing import Iterable


DISALLOWED_PATTERNS = (
    "how to make a bomb",
    "harm yourself",
    "suicide instructions",
)


def contains_disallowed_content(text: str, patterns: Iterable[str] = DISALLOWED_PATTERNS) -> bool:
    """Return True when text contains disallowed patterns."""

    normalized = text.lower()
    return any(pattern in normalized for pattern in patterns)
