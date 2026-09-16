from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]
