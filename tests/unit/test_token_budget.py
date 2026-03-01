from uuid import uuid4

from her.agents.token_budget import TokenBudgetManager


def test_token_budget_drops_old_messages_when_needed() -> None:
    manager = TokenBudgetManager(max_input_tokens=120)
    session_id = uuid4()

    messages = [{"role": "user", "content": f"message {index} " * 15} for index in range(10)]
    window = manager.build_window(
        session_id=session_id,
        base_system_prompt="System prompt",
        context_sections=["Context section"],
        messages=messages,
    )

    assert window.dropped_messages > 0
    assert len(window.messages) < len(messages)
    assert manager.session_tokens(session_id) > 0
