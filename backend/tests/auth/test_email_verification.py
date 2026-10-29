from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.auth.repo import AuthRepository, UserRecord
from tests.conftest import auth_headers

PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "another-correct-password"


@pytest.fixture
def request_code(client, api_prefix):
    def request(email="reader@example.com", purpose="register"):
        return client.post(
            f"{api_prefix}/auth/email-codes", json={"email": email, "purpose": purpose}
        )

    return request


@pytest.fixture
def verify_code(client, api_prefix):
    def verify(challenge, code, purpose="register"):
        return client.post(
            f"{api_prefix}/auth/email-codes/verify",
            json={"challenge_id": challenge, "code": code, "purpose": purpose},
        )

    return verify


@pytest.fixture
def expire_cooldown(email_verification_store):
    def expire():
        store = email_verification_store
        for key in store.redis.scan_iter(match=store.namespace + ":cooldown:*"):
            store.redis.delete(key)

    return expire


@pytest.fixture
def grant(request_code, verify_code, auth_emails, expire_cooldown):
    def issue(email="reader@example.com", purpose="register"):
        expire_cooldown()
        requested = request_code(email, purpose)
        assert requested.status_code == 200, requested.text
        verified = verify_code(
            requested.json()["challenge_id"], auth_emails[-1]["code"], purpose
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["expires_in"] == 600
        return verified.json()["verification_token"]

    return issue


def registration_payload(token, password=PASSWORD):
    return {
        "verification_token": token,
        "password": password,
        "password_confirmation": password,
    }


def test_registration_rejects_unverified_email_when_old_contract_is_used(
    client, api_prefix
):
    response = client.post(
        f"{api_prefix}/auth/register",
        json={"email": "unverified@example.com", "password": PASSWORD},
    )
    assert response.status_code == 422


def test_email_code_creates_verified_account_when_code_is_correct(
    client, api_prefix, request_code, verify_code, auth_emails, db_session
):
    before = datetime.now(UTC)
    response = request_code("Verified@Example.com")
    assert response.status_code == 200
    assert response.json()["retry_after"] == 60
    assert response.json()["expires_in"] == 600
    assert db_session.scalar(select(UserRecord)) is None
    verified = verify_code(response.json()["challenge_id"], auth_emails[-1]["code"])
    assert verified.status_code == 200
    assert db_session.scalar(select(UserRecord)) is None
    registered = client.post(
        f"{api_prefix}/auth/register",
        json=registration_payload(verified.json()["verification_token"]),
    )
    assert registered.status_code == 201
    user = db_session.scalar(select(UserRecord))
    assert user.email == "verified@example.com"
    assert user.email_verified_at >= before


@pytest.mark.parametrize("email", ["reader@example.com", "Reader@Example.com"])
def test_registration_code_returns_conflict_when_email_is_already_registered(
    request_code, make_user, auth_emails, email_verification_store, email
):
    make_user()
    response = request_code(email)
    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"
    assert not auth_emails
    store = email_verification_store
    assert not list(store.redis.scan_iter(match=store.namespace + ":*"))


def test_challenge_stores_no_plaintext_code_when_email_is_requested(
    request_code, auth_emails, email_verification_store
):
    response = request_code()
    assert response.status_code == 200
    store = email_verification_store
    keys = list(store.redis.scan_iter(match=store.namespace + ":challenge:*"))
    assert len(keys) == 1
    values = store.redis.hgetall(keys[0])
    assert b"code" not in values
    assert values[b"digest"] != auth_emails[-1]["code"].encode()
    assert 590 <= store.redis.ttl(keys[0]) <= 600


def test_challenge_becomes_unusable_when_five_codes_are_wrong(
    request_code, verify_code, auth_emails
):
    challenge = request_code().json()["challenge_id"]
    correct = auth_emails[-1]["code"]
    wrong = "000000" if correct != "000000" else "111111"
    for _ in range(5):
        assert verify_code(challenge, wrong).status_code == 422
    assert verify_code(challenge, correct).status_code == 422
    assert request_code().status_code == 429


def test_old_code_is_invalid_when_challenge_is_resent(
    request_code, verify_code, auth_emails, expire_cooldown
):
    first = request_code().json()["challenge_id"]
    old_code = auth_emails[-1]["code"]
    expire_cooldown()
    second = request_code().json()["challenge_id"]
    assert verify_code(first, old_code).status_code == 422
    assert verify_code(second, auth_emails[-1]["code"]).status_code == 200


def test_email_limit_survives_challenge_deletion_when_five_emails_are_sent(
    request_code, expire_cooldown
):
    for _ in range(5):
        expire_cooldown()
        assert request_code().status_code == 200
    expire_cooldown()
    assert request_code(purpose="password_reset").status_code == 429


def test_ip_limit_is_shared_when_twenty_distinct_emails_are_requested(request_code):
    for index in range(20):
        assert request_code(f"user{index}@example.com").status_code == 200
    assert request_code("other@example.com").status_code == 429


def test_challenge_is_consumed_once_when_verifications_are_concurrent(
    request_code, verify_code, auth_emails
):
    challenge = request_code().json()["challenge_id"]
    code = auth_emails[-1]["code"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(lambda _: verify_code(challenge, code).status_code, range(2))
        )
    assert sorted(statuses) == [200, 422]


def test_grant_is_consumed_once_when_registrations_are_concurrent(
    client, api_prefix, grant
):
    payload = registration_payload(grant())
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda _: (
                    client.post(f"{api_prefix}/auth/register", json=payload).status_code
                ),
                range(2),
            )
        )
    assert sorted(statuses) == [201, 422]


def test_duplicate_registration_returns_conflict_when_distinct_grants_race(
    client, api_prefix, grant
):
    tokens = [grant(), grant()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda token: (
                    client.post(
                        f"{api_prefix}/auth/register", json=registration_payload(token)
                    ).status_code
                ),
                tokens,
            )
        )
    assert sorted(statuses) == [201, 409]


def test_reset_consumes_grant_once_when_requests_are_concurrent(
    client, api_prefix, register_user, grant
):
    register_user()
    payload = registration_payload(grant(purpose="password_reset"), NEW_PASSWORD)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda _: (
                    client.post(
                        f"{api_prefix}/auth/password-reset", json=payload
                    ).status_code
                ),
                range(2),
            )
        )
    assert sorted(statuses) == [204, 422]


def test_reset_grant_cannot_create_account_when_purpose_does_not_match(
    client, api_prefix, register_user, grant
):
    register_user()
    payload = registration_payload(grant(purpose="password_reset"), NEW_PASSWORD)
    assert client.post(f"{api_prefix}/auth/register", json=payload).status_code == 422
    assert (
        client.post(f"{api_prefix}/auth/password-reset", json=payload).status_code
        == 204
    )


def test_verification_fails_closed_when_redis_is_unavailable(
    client, api_prefix, email_verification_store, monkeypatch
):
    from redis.exceptions import ConnectionError

    def unavailable(*args, **kwargs):
        raise ConnectionError("unavailable")

    monkeypatch.setattr(email_verification_store.redis, "eval", unavailable)
    response = client.post(
        f"{api_prefix}/auth/email-codes/verify",
        json={"challenge_id": "unavailable", "code": "123456", "purpose": "register"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "provider_unavailable"


def test_password_confirmation_preserves_grant_when_values_do_not_match(
    client, api_prefix, grant
):
    payload = registration_payload(grant())
    response = client.post(
        f"{api_prefix}/auth/register",
        json=dict(payload, password_confirmation="a-different-password"),
    )
    assert response.status_code == 422
    assert client.post(f"{api_prefix}/auth/register", json=payload).status_code == 201


def test_register_grant_cannot_reset_password_when_purpose_does_not_match(
    client, api_prefix, grant
):
    payload = registration_payload(grant())
    assert (
        client.post(f"{api_prefix}/auth/password-reset", json=payload).status_code
        == 422
    )
    assert client.post(f"{api_prefix}/auth/register", json=payload).status_code == 201


def test_challenge_is_invalid_when_purpose_does_not_match(
    request_code, verify_code, auth_emails
):
    challenge = request_code().json()["challenge_id"]
    assert (
        verify_code(challenge, auth_emails[-1]["code"], "password_reset").status_code
        == 422
    )


def test_challenge_is_invalid_when_redis_expiration_has_elapsed(
    request_code, verify_code, auth_emails, email_verification_store
):
    challenge = request_code().json()["challenge_id"]
    store = email_verification_store
    for key in store.redis.scan_iter(match=store.namespace + ":challenge:*"):
        store.redis.pexpire(key, 0)
    assert verify_code(challenge, auth_emails[-1]["code"]).status_code == 422


def test_grant_is_invalid_when_redis_expiration_has_elapsed(
    client, api_prefix, grant, email_verification_store
):
    token = grant()
    store = email_verification_store
    for key in store.redis.scan_iter(match=store.namespace + ":grant:*"):
        assert 590 <= store.redis.ttl(key) <= 600
        store.redis.pexpire(key, 0)
    assert (
        client.post(
            f"{api_prefix}/auth/register", json=registration_payload(token)
        ).status_code
        == 422
    )


def test_unknown_reset_email_gets_virtual_challenge_when_no_account_exists(
    request_code, verify_code, auth_emails, monkeypatch
):
    monkeypatch.setattr("app.auth.repo.secrets.randbelow", lambda _: 123456)
    response = request_code("unknown@example.com", "password_reset")
    assert response.status_code == 200
    assert set(response.json()) == {"challenge_id", "retry_after", "expires_in"}
    assert not auth_emails
    assert (
        verify_code(
            response.json()["challenge_id"], "123456", "password_reset"
        ).status_code
        == 422
    )


def test_reset_revokes_every_session_when_password_changes(
    client, api_prefix, register_user, grant, auth_emails
):
    first = register_user()
    first_refresh = client.cookies["paper_agent_refresh"]
    second = client.post(
        f"{api_prefix}/auth/login",
        json={"email": "reader@example.com", "password": PASSWORD},
    ).json()
    second_refresh = client.cookies["paper_agent_refresh"]
    token = grant(purpose="password_reset")
    response = client.post(
        f"{api_prefix}/auth/password-reset",
        json=registration_payload(token, NEW_PASSWORD),
    )
    assert response.status_code == 204
    assert response.content == b""
    assert auth_emails[-1]["kind"] == "password_reset"
    for session in (first, second):
        assert (
            client.get(
                f"{api_prefix}/auth/session-status",
                headers=auth_headers(session["access_token"]),
            ).status_code
            == 401
        )
    for refresh in (first_refresh, second_refresh):
        client.cookies.set("paper_agent_refresh", refresh)
        assert client.post(f"{api_prefix}/auth/refresh").status_code == 401
    assert (
        client.post(
            f"{api_prefix}/auth/login",
            json={"email": "reader@example.com", "password": PASSWORD},
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"{api_prefix}/auth/login",
            json={"email": "reader@example.com", "password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{api_prefix}/auth/password-reset",
            json=registration_payload(token, NEW_PASSWORD),
        ).status_code
        == 422
    )


def test_old_reset_grant_is_invalid_when_another_grant_changed_password(
    client, api_prefix, register_user, grant
):
    register_user()
    first = grant(purpose="password_reset")
    second = grant(purpose="password_reset")
    assert (
        client.post(
            f"{api_prefix}/auth/password-reset",
            json=registration_payload(first, NEW_PASSWORD),
        ).status_code
        == 204
    )
    assert (
        client.post(
            f"{api_prefix}/auth/password-reset", json=registration_payload(second)
        ).status_code
        == 422
    )


def test_reset_keeps_grant_and_session_when_confirmation_does_not_match(
    client, api_prefix, register_user, grant
):
    original = register_user()
    payload = registration_payload(grant(purpose="password_reset"), NEW_PASSWORD)
    rejected = client.post(
        f"{api_prefix}/auth/password-reset",
        json=dict(payload, password_confirmation=PASSWORD),
    )
    assert rejected.status_code == 422
    assert (
        client.get(
            f"{api_prefix}/auth/session-status",
            headers=auth_headers(original["access_token"]),
        ).status_code
        == 200
    )
    assert (
        client.post(f"{api_prefix}/auth/password-reset", json=payload).status_code
        == 204
    )


def test_reset_rolls_back_but_burns_grant_when_security_email_cannot_be_enqueued(
    client, api_prefix, register_user, grant, monkeypatch
):
    original = register_user()
    token = grant(purpose="password_reset")

    def unavailable(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(AuthRepository, "enqueue_password_reset_email", unavailable)
        with pytest.raises(RuntimeError, match="outbox unavailable"):
            client.post(
                f"{api_prefix}/auth/password-reset",
                json=registration_payload(token, NEW_PASSWORD),
            )
    assert (
        client.post(
            f"{api_prefix}/auth/password-reset",
            json=registration_payload(token, NEW_PASSWORD),
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{api_prefix}/auth/session-status",
            headers=auth_headers(original["access_token"]),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{api_prefix}/auth/login",
            json={"email": "reader@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )


def test_session_status_returns_only_user_id_when_session_is_active(
    client, api_prefix, register_user
):
    session = register_user()
    response = client.get(
        f"{api_prefix}/auth/session-status",
        headers=auth_headers(session["access_token"]),
    )
    assert response.json() == {"user_id": session["user"]["id"]}
    assert client.get(f"{api_prefix}/auth/session-status").status_code == 401


def test_challenge_is_unusable_when_email_transaction_fails(
    client, request_code, verify_code, auth_emails, monkeypatch
):
    captured = []
    from app.auth.repo import EmailVerificationStore

    original = EmailVerificationStore.issue

    def capture(store, **kwargs):
        result = original(store, **kwargs)
        captured.append(result)
        return result

    def unavailable(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(EmailVerificationStore, "issue", capture)
    monkeypatch.setattr(AuthRepository, "enqueue_verification_email", unavailable)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        request_code()
    challenge, code = captured[0]
    assert verify_code(challenge, code).status_code == 422
    assert request_code().status_code == 429
