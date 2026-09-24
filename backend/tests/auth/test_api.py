from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.repo import AuthSessionRecord, RefreshTokenRecord
from tests.conftest import auth_headers

PASSWORD = "correct-horse-battery"


def test_register_login_refresh_and_logout(client: TestClient, api_prefix: str) -> None:
    register = client.post(
        f"{api_prefix}/auth/register",
        json={
            "email": "Reader@Example.com",
            "password": PASSWORD,
            "display_name": "  Reader  ",
        },
    )
    assert register.status_code == 201, register.text
    body = register.json()
    assert body["user"]["email"] == "reader@example.com"
    assert body["user"]["display_name"] == "Reader"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    UUID(body["user"]["id"])
    assert client.cookies.get("paper_agent_refresh")

    me = client.get(
        f"{api_prefix}/auth/me",
        headers=auth_headers(body["access_token"]),
    )
    assert me.status_code == 200
    assert me.json()["email"] == "reader@example.com"

    refreshed = client.post(f"{api_prefix}/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["access_token"] != body["access_token"]

    logged_out = client.post(f"{api_prefix}/auth/logout")
    assert logged_out.status_code == 204
    assert not client.cookies.get("paper_agent_refresh")

    after_logout = client.get(
        f"{api_prefix}/auth/me",
        headers=auth_headers(body["access_token"]),
    )
    assert after_logout.status_code == 401
    assert after_logout.json()["code"] == "unauthorized"


def test_login_rejects_wrong_credentials_and_unknown_email(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    register_user(email="reader@example.com", password=PASSWORD)

    wrong_password = client.post(
        f"{api_prefix}/auth/login",
        json={"email": "reader@example.com", "password": "wrong-password"},
    )
    unknown_email = client.post(
        f"{api_prefix}/auth/login",
        json={"email": "nobody@example.com", "password": PASSWORD},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["code"] == "invalid_credentials"
    assert unknown_email.json()["code"] == "invalid_credentials"


def test_duplicate_email_is_rejected(client: TestClient, api_prefix: str) -> None:
    payload = {"email": "reader@example.com", "password": PASSWORD}
    first = client.post(f"{api_prefix}/auth/register", json=payload)
    second = client.post(f"{api_prefix}/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "email_already_registered"


def test_replayed_refresh_token_revokes_the_family(
    client: TestClient,
    api_prefix: str,
    db_session: Session,
) -> None:
    register = client.post(
        f"{api_prefix}/auth/register",
        json={"email": "reader@example.com", "password": PASSWORD},
    )
    first_token = register.cookies["paper_agent_refresh"]

    rotated = client.post(f"{api_prefix}/auth/refresh")
    assert rotated.status_code == 200
    second_token = client.cookies["paper_agent_refresh"]
    assert second_token != first_token

    # Replaying the already-rotated token must be treated as theft.
    client.cookies.set("paper_agent_refresh", first_token)
    replay = client.post(f"{api_prefix}/auth/refresh")
    assert replay.status_code == 401
    assert replay.json()["code"] == "refresh_token_reused"

    client.cookies.set("paper_agent_refresh", second_token)
    after_replay = client.post(f"{api_prefix}/auth/refresh")
    assert after_replay.status_code == 401

    sessions = db_session.scalars(select(AuthSessionRecord)).all()
    assert len(sessions) == 1
    assert sessions[0].revoked_at is not None
    tokens = db_session.scalars(select(RefreshTokenRecord)).all()
    assert len(tokens) == 2


def test_refresh_requires_cookie_and_rejects_foreign_origin(
    client: TestClient,
    api_prefix: str,
) -> None:
    client.post(
        f"{api_prefix}/auth/register",
        json={"email": "reader@example.com", "password": PASSWORD},
    )
    client.cookies.clear()

    missing = client.post(f"{api_prefix}/auth/refresh")
    assert missing.status_code == 401
    assert missing.json()["code"] == "refresh_token_missing"

    client.post(
        f"{api_prefix}/auth/login",
        json={"email": "reader@example.com", "password": PASSWORD},
    )
    foreign = client.post(
        f"{api_prefix}/auth/refresh",
        headers={"Origin": "https://evil.example.com"},
    )
    assert foreign.status_code == 403
    assert foreign.json()["code"] == "origin_not_allowed"


def test_expired_refresh_token_is_rejected(
    client: TestClient,
    api_prefix: str,
    db_session: Session,
) -> None:
    client.post(
        f"{api_prefix}/auth/register",
        json={"email": "reader@example.com", "password": PASSWORD},
    )
    past = datetime.now(UTC) - timedelta(minutes=1)
    for session in db_session.scalars(select(AuthSessionRecord)).all():
        session.expires_at = past
    for token in db_session.scalars(select(RefreshTokenRecord)).all():
        token.expires_at = past
    db_session.commit()

    response = client.post(f"{api_prefix}/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == "refresh_token_invalid"


def test_protected_endpoints_require_valid_access_token(
    client: TestClient,
    api_prefix: str,
) -> None:
    anonymous = client.get(f"{api_prefix}/auth/me")
    malformed = client.get(
        f"{api_prefix}/auth/me",
        headers=auth_headers("not-a-jwt"),
    )

    assert anonymous.status_code == 401
    assert malformed.status_code == 401
    assert anonymous.json()["code"] == "unauthorized"


def test_registration_validates_email_and_password_policy(
    client: TestClient,
    api_prefix: str,
) -> None:
    invalid_email = client.post(
        f"{api_prefix}/auth/register",
        json={"email": "not-an-email", "password": PASSWORD},
    )
    short_password = client.post(
        f"{api_prefix}/auth/register",
        json={"email": "reader@example.com", "password": "short"},
    )

    assert invalid_email.status_code == 422
    assert short_password.status_code == 422
    assert invalid_email.json()["code"] == "validation_error"
