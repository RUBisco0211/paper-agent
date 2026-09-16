from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.main import create_app
from app.platform.errors import ErrorCode, NotFoundError


def _app_with_routes() -> FastAPI:
    app = create_app()

    @app.get("/boom/expected")
    def expected_failure() -> None:
        raise NotFoundError("论文不存在", code=ErrorCode.PAPER_NOT_FOUND)

    @app.get("/boom/http")
    def http_failure() -> None:
        raise HTTPException(status_code=403, detail="没有访问该资源的权限")

    @app.get("/boom/unexpected")
    def unexpected_failure() -> None:
        raise RuntimeError("database exploded")

    return app


def test_error_contract_is_stable_and_correlated() -> None:
    app = _app_with_routes()
    with TestClient(app, raise_server_exceptions=False) as client:
        expected = client.get(
            "/boom/expected",
            headers={"X-Request-ID": "0123456789abcdef0123456789abcdef"},
        )
        forbidden = client.get(
            "/boom/http", headers={"X-Request-ID": "1123456789abcdef0123456789abcdef"}
        )
        unexpected = client.get(
            "/boom/unexpected",
            headers={"X-Request-ID": "2123456789abcdef0123456789abcdef"},
        )

    assert expected.status_code == 404
    assert expected.json() == {
        "code": "paper_not_found",
        "message": "论文不存在",
        "request_id": "0123456789abcdef0123456789abcdef",
    }
    assert expected.headers["X-Request-ID"] == "0123456789abcdef0123456789abcdef"

    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden"
    assert forbidden.json()["request_id"] == "1123456789abcdef0123456789abcdef"

    assert unexpected.status_code == 500
    assert unexpected.json() == {
        "code": "internal_error",
        "message": "服务内部错误",
        "request_id": "2123456789abcdef0123456789abcdef",
    }
    assert unexpected.headers["X-Request-ID"] == "2123456789abcdef0123456789abcdef"


def test_validation_errors_include_details() -> None:
    app = _app_with_routes()

    @app.get("/boom/validated")
    def validated(limit: int) -> dict[str, int]:
        return {"limit": limit}

    with TestClient(app) as local_client:
        response = local_client.get("/boom/validated", params={"limit": "abc"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["details"]
    assert body["request_id"]
