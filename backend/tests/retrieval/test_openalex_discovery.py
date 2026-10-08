from uuid import uuid4

from fastapi.testclient import TestClient

from app.platform.config import settings
from app.platform.discovery import DiscoveryResult
from app.retrieval.depends import get_discovery_adapter
from tests.conftest import auth_headers


class FakeOpenAlex:
    def search(self, query: str, limit: int) -> list[dict]:
        assert query == "multi-agent safety"
        assert limit == 2
        return DiscoveryResult(
            papers=[
                {
                    "title": "Safety paper",
                    "doi": "10.1234/example",
                    "source_id": "https://openalex.org/W1",
                    "openalex_id": "https://openalex.org/W1",
                    "year": 2025,
                    "authors": ["A. Author"],
                    "url": "https://example.org/paper",
                }
            ],
            failed_sources=[],
        )


def test_discovery_returns_external_candidates_without_citations_when_session_is_bound(
    client: TestClient, api_prefix: str, register_user, monkeypatch
) -> None:
    owner = register_user(email="discover-owner@example.com")
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    client.app.dependency_overrides[get_discovery_adapter] = FakeOpenAlex
    try:
        response = client.post(
            f"{api_prefix}/internal/discover-papers",
            headers={"X-Agent-Internal-Key": "a" * 64},
            json={
                "user_id": owner["user"]["id"],
                "session_id": session_id,
                "query": "multi-agent safety",
                "limit": 2,
            },
        )
    finally:
        client.app.dependency_overrides.pop(get_discovery_adapter, None)

    assert response.status_code == 200
    assert response.json()["papers"][0]["doi"] == "10.1234/example"
    assert "citation_id" not in response.text


def test_discovery_rejects_an_unbound_session_before_calling_openalex(
    client: TestClient, api_prefix: str, register_user, monkeypatch
) -> None:
    owner = register_user(email="discover-unbound@example.com")
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    response = client.post(
        f"{api_prefix}/internal/discover-papers",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json={
            "user_id": owner["user"]["id"],
            "session_id": str(uuid4()),
            "query": "multi-agent safety",
            "limit": 2,
        },
    )
    assert response.status_code == 404
