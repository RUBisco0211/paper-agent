from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_business_service_has_no_legacy_chat_route_when_agentscope_owns_sessions(
    client: TestClient, api_prefix: str, register_user
) -> None:
    token = register_user(email="no-legacy-chat@example.com")["access_token"]

    response = client.get(f"{api_prefix}/sessions", headers=auth_headers(token))

    assert response.status_code == 404
