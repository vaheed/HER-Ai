from her.config.settings import Settings
from her.embeddings.base import normalize_dimensions
from her.embeddings.custom_provider import CustomEmbeddingProvider
from her.embeddings.ollama_provider import OllamaEmbeddingProvider
from her.embeddings.service import build_embedding_provider


def test_normalize_dimensions_pad_and_truncate() -> None:
    padded = normalize_dimensions([1.0, 2.0], 4)
    truncated = normalize_dimensions([1.0, 2.0, 3.0], 2)

    assert padded == [1.0, 2.0, 0.0, 0.0]
    assert truncated == [1.0, 2.0]


def test_build_embedding_provider_defaults_to_ollama() -> None:
    settings = Settings(embedding_provider="ollama")
    provider = build_embedding_provider(settings)

    assert isinstance(provider, OllamaEmbeddingProvider)


def test_build_embedding_provider_custom() -> None:
    settings = Settings(
        embedding_provider="custom",
        custom_embedding_endpoint="https://example.com/embeddings",
    )
    provider = build_embedding_provider(settings)

    assert isinstance(provider, CustomEmbeddingProvider)


def test_build_embedding_provider_none() -> None:
    settings = Settings(embedding_provider="none")
    provider = build_embedding_provider(settings)

    assert provider is None
