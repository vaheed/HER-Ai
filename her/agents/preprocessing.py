from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal


Intent = Literal["question", "goal_update", "reflection", "task", "general"]
Sentiment = Literal["positive", "neutral", "negative"]

POSITIVE_WORDS = {"great", "thanks", "awesome", "love", "good", "perfect", "helpful"}
NEGATIVE_WORDS = {"bad", "hate", "wrong", "angry", "upset", "frustrated", "annoyed"}


@dataclass
class ProcessedInput:
    """Normalized and enriched representation of user input."""

    raw_text: str
    sanitized_text: str
    tokens: List[str]
    sentiment: Sentiment
    intent: Intent
    entities: List[str] = field(default_factory=list)
    bias_signals: List[str] = field(default_factory=list)


async def preprocess_input(text: str) -> ProcessedInput:
    """Run lightweight preprocessing pipeline for user input."""

    sanitized = sanitize_text(text)
    tokens = tokenize(sanitized)
    sentiment = detect_sentiment(tokens)
    intent = classify_intent(sanitized, tokens)
    entities = extract_entities(text)
    bias_signals = detect_bias_signals(sanitized)

    return ProcessedInput(
        raw_text=text,
        sanitized_text=sanitized,
        tokens=tokens,
        sentiment=sentiment,
        intent=intent,
        entities=entities,
        bias_signals=bias_signals,
    )


def sanitize_text(text: str) -> str:
    """Normalize whitespace and strip non-printable characters."""

    without_control = "".join(char for char in text if char.isprintable() or char.isspace())
    collapsed = re.sub(r"\s+", " ", without_control).strip()
    return collapsed


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric tokens."""

    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def detect_sentiment(tokens: List[str]) -> Sentiment:
    """Estimate sentiment with a simple lexical heuristic."""

    positive = sum(1 for token in tokens if token in POSITIVE_WORDS)
    negative = sum(1 for token in tokens if token in NEGATIVE_WORDS)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def classify_intent(text: str, tokens: List[str]) -> Intent:
    """Classify interaction intent using rules."""

    lowered = text.lower()
    if "goal" in tokens or lowered.startswith("/goals"):
        return "goal_update"
    if "reflect" in tokens or lowered.startswith("/reflect"):
        return "reflection"
    if "?" in text:
        return "question"
    if any(token in {"build", "create", "implement", "fix", "add"} for token in tokens):
        return "task"
    return "general"


def extract_entities(text: str) -> List[str]:
    """Extract coarse named entities from user input."""

    entities = set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text))
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", text)
    entities.update(emails)
    return sorted(entities)


def detect_bias_signals(text: str) -> List[str]:
    """Detect simple contradiction/avoidance signals."""

    signals: List[str] = []
    lowered = text.lower()
    if "never" in lowered and "always" in lowered:
        signals.append("self-contradiction")
    if any(fragment in lowered for fragment in ("don't want", "skip this", "avoid")):
        signals.append("avoidance")
    if any(fragment in lowered for fragment in ("you said", "contradict", "inconsistent")):
        signals.append("value-contradiction")
    return signals


def processed_summary(processed: ProcessedInput) -> Dict[str, str]:
    """Return concise summary fields for prompt context."""

    return {
        "intent": processed.intent,
        "sentiment": processed.sentiment,
        "entities": ", ".join(processed.entities[:5]) if processed.entities else "none",
        "bias": ", ".join(processed.bias_signals) if processed.bias_signals else "none",
    }
