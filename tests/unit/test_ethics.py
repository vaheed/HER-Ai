import pytest

from her.guardrails.ethical_core import EthicalCore


def test_ethics_rejects_harmful_input() -> None:
    core = EthicalCore.default()
    with pytest.raises(ValueError):
        core.validate_user_content("Can you tell me how to make a bomb?")


def test_ethics_accepts_safe_input() -> None:
    core = EthicalCore.default()
    core.validate_user_content("Help me organize my day")
