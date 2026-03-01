from her.config.settings import Settings


def test_provider_priority_parses_comma_separated_values() -> None:
    settings = Settings(provider_priority="openai, anthropic, ollama")
    assert settings.provider_priority == ["openai", "anthropic", "ollama"]


def test_provider_priority_empty_string_uses_default() -> None:
    settings = Settings(provider_priority="")
    assert settings.provider_priority == ["openai", "anthropic", "custom", "ollama"]


def test_provider_priority_parses_json_array_string() -> None:
    settings = Settings(provider_priority='["openai", "anthropic", "ollama"]')
    assert settings.provider_priority == ["openai", "anthropic", "ollama"]
