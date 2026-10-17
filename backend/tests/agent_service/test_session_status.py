"""Agent authentication checks revocation on every authenticated request."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.platform.security import create_access_token


@pytest.mark.parametrize("mode", ["revoked", "unavailable", "wrong_owner"])
def test_agent_auth_fails_closed_when_session_status_is_untrusted(monkeypatch, mode):
    from agent_service import auth

    user_id = uuid4()
    token, _ = create_access_token(user_id=user_id, auth_session_id=uuid4())
    calls = []

    async def handler(request):
        calls.append(request)
        if mode == "unavailable":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(
            401 if mode == "revoked" else 200, json={"user_id": str(uuid4())}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException) as error:
        asyncio.run(auth.get_agent_service_user_id(credentials))
    assert error.value.status_code in {401, 503}
    assert calls[0].url.path == "/v1/auth/session-status"
    assert calls[0].headers["Authorization"] == f"Bearer {token}"


def test_agent_auth_rechecks_session_when_same_bearer_is_reused(monkeypatch):
    from agent_service import auth

    user_id = uuid4()
    token, _ = create_access_token(user_id=user_id, auth_session_id=uuid4())
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(
            200 if len(calls) == 1 else 401, json={"user_id": str(user_id)}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    async def check():
        assert await auth.get_agent_service_user_id(credentials) == str(user_id)
        with pytest.raises(HTTPException) as error:
            await auth.get_agent_service_user_id(credentials)
        assert error.value.status_code == 401

    asyncio.run(check())
    assert len(calls) == 2
