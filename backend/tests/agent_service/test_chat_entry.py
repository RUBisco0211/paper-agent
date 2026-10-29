"""The single /chat/ entry validates references and still serves plain chat."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.platform.config import settings
from tests.conftest import _ensure_database, _truncate_all


@pytest.fixture(scope="module")
def chat_entry_client(tmp_path_factory):
    from agent_service.main import create_agent_service_app

    database_url = (
        make_url(settings.resolved_test_database_url)
        .set(database="paper_agent_chat_entry_test")
        .render_as_string(hide_password=False)
    )
    _ensure_database(database_url)
    engine = create_engine(database_url)
    _truncate_all(engine)
    engine.dispose()
    app = create_agent_service_app(database_url, tmp_path_factory.mktemp("chat-entry"))
    from agentscope.app.deps import get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: str(uuid4())
    with TestClient(app) as client:
        yield client


def test_chat_entry_rejects_a_reference_to_an_unknown_session(chat_entry_client):
    response = chat_entry_client.post(
        "/chat/",
        json={
            "agent_id": str(uuid4()),
            "session_id": str(uuid4()),
            "text": "@{{1}} 讲了什么",
            "mentions": [{"index": 1, "user_paper_id": str(uuid4())}],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "session_not_found"


def test_chat_entry_delegates_a_plain_message_to_the_builtin_route(chat_entry_client):
    response = chat_entry_client.post(
        "/chat/",
        json={
            "agent_id": str(uuid4()),
            "session_id": str(uuid4()),
            "input": {
                "id": uuid4().hex,
                "name": "user",
                "role": "user",
                "content": [{"type": "text", "text": "hi"}],
            },
        },
    )

    # The built-in handler accepts the trigger even for an unknown session and
    # fails later inside the run; a 200 here is the proof this request was
    # delegated rather than validated by the reference path.
    assert response.status_code == 200
    assert response.json()["status"] == "started"
