from her.config.settings import Settings


def test_provider_priority_parses_comma_separated_values() -> None:
    settings = Settings(provider_priority="openai, anthropic, ollama")
    assert settings.provider_priority == ["openai", "anthropic", "ollama"]
