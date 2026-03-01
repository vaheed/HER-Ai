from fastapi.testclient import TestClient

from her.config.settings import get_settings
from her.interfaces.api.main import create_app


def test_state_route() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/state")
        assert response.status_code == 200
        payload = response.json()
        assert "personality" in payload
        assert "emotion" in payload


def test_memory_search_route_without_embedding_provider() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/memory/search", params={"q": "test memory"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["query"] == "test memory"
        assert "items" in payload


def test_goals_route() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/goals")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
