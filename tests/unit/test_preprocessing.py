import pytest

from her.agents.preprocessing import (
    classify_intent,
    detect_bias_signals,
    preprocess_input,
    sanitize_text,
)


def test_sanitize_text_removes_extra_whitespace() -> None:
    assert sanitize_text(" hello\n\nworld \t test ") == "hello world test"


def test_classify_intent_question() -> None:
    intent = classify_intent("How does this work?", ["how", "does", "this", "work"])
    assert intent == "question"


def test_detect_bias_signals() -> None:
    signals = detect_bias_signals("You said this before but now contradict and I want to avoid it")
    assert "value-contradiction" in signals
    assert "avoidance" in signals


@pytest.mark.asyncio
async def test_preprocess_input_pipeline() -> None:
    processed = await preprocess_input("Please build this for Acme Corp, thanks!")
    assert processed.intent == "task"
    assert processed.sentiment == "positive"
    assert "Acme Corp" in processed.entities
