from pathlib import Path

import yaml


def test_agents_config_has_required_sections() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config" / "agents.yaml"
    data = yaml.safe_load(config_path.read_text())
    assert "conversation_agent" in data
    assert "reflection_agent" in data
    assert "personality_agent" in data
