from fastapi.testclient import TestClient

from app.platform.discovery import DiscoveryResult
from app.imports.depends import get_discovery_adapter
from tests.conftest import auth_headers


class FakeDiscovery:
    def search(self, query: str, limit: int) -> DiscoveryResult:
        assert query == "agent safety"
        assert limit == 3
        return DiscoveryResult(
            papers=[
                {
                    "source_id": "https://doi.org/10.1234/safety",
                    "title": "Agent Safety",
                    "doi": "10.1234/safety",
                    "pdf_url": "https://example.org/safety.pdf",
                    "sources": ["crossref"],
                }
            ],
            failed_sources=["openalex"],
        )


def test_manual_discovery_returns_candidates_without_a_session_when_authenticated(
    client: TestClient, api_prefix: str, register_user
) -> None:
    owner = register_user(email="manual-discovery@example.com")
    client.app.dependency_overrides[get_discovery_adapter] = FakeDiscovery
    try:
        response = client.post(
            f"{api_prefix}/discover-papers",
            headers=auth_headers(owner["access_token"]),
            json={"query": "agent safety", "limit": 3},
        )
    finally:
        client.app.dependency_overrides.pop(get_discovery_adapter, None)
    assert response.status_code == 200
    assert response.json()["papers"][0]["pdf_url"] == "https://example.org/safety.pdf"
    assert response.json()["failed_sources"] == ["openalex"]
    assert "candidate_token" not in response.text


def test_manual_discovery_requires_login(client: TestClient, api_prefix: str) -> None:
    response = client.post(
        f"{api_prefix}/discover-papers",
        json={"query": "agent safety", "limit": 3},
    )
    assert response.status_code == 401
