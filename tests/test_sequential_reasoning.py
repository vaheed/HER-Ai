from pathlib import Path


def test_autonomous_operator_uses_bounded_plan_act_verify_loop() -> None:
    source = Path("her-core/her_telegram/autonomous_operator.py").read_text()

    assert '"event": "agent_step"' in source
    assert 'event_type="agent_step"' in source
    assert "while steps < min(self._max_steps, 5)" in source
    assert "def _verify_step" in source
    assert "def _validate_command" in source
    assert "Execution stopped due to repeated identical command." in source

