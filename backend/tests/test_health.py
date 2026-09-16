from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
    assert response.headers["X-Request-ID"]


def test_versioned_health_endpoint(client: TestClient, api_prefix: str) -> None:
    response = client.get(f"{api_prefix}/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
