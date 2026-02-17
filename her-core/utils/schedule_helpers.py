"""Shared helpers for schedule parsing and normalization."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

_CLOCK_PATTERN = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)

_WEEKDAY_MAPPING = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def extract_json_object(raw: str) -> dict[str, Any] | None:
    """Extract and parse a JSON object from raw model output."""
    text = str(raw or "").strip()
    if not text:
        return None

    cleaned = text
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def normalize_weekdays_input(raw: Any) -> list[int]:
    """Normalize mixed weekday tokens to [0..6]."""
    if not isinstance(raw, list):
        return []

    normalized: set[int] = set()
    for item in raw:
        if isinstance(item, int) and 0 <= item <= 6:
            normalized.add(item)
            continue
        text = str(item).strip().lower()
        if text in _WEEKDAY_MAPPING:
            normalized.add(_WEEKDAY_MAPPING[text])
    return sorted(normalized)


def parse_clock(text: str) -> tuple[int, int] | None:
    """Parse clock expressions such as 'at 9', 'at 09:30', 'at 7pm'."""
    match = _CLOCK_PATTERN.search(text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridian = (match.group(3) or "").lower()
    if meridian == "pm" and hour < 12:
        hour += 12
    if meridian == "am" and hour == 12:
        hour = 0
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def interval_unit_to_base(unit: str) -> str:
    """Map short units to scheduler bases."""
    lower = unit.strip().lower()
    if lower in {"m", "min", "mins", "minute", "minutes"}:
        return "minutes"
    if lower in {"h", "hr", "hrs", "hour", "hours"}:
        return "hours"
    return "days"


def parse_relative_delta(value: int, unit: str) -> timedelta:
    """Convert interval numeric + unit into a timedelta."""
    base = interval_unit_to_base(unit)
    if base == "minutes":
        return timedelta(minutes=value)
    if base == "hours":
        return timedelta(hours=value)
    return timedelta(days=value)
