import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.sessions.agent import AgentEvent, AgentEventType, AgentRunner
from tests.conftest import auth_headers, install_agent_runner

VALID_LLM_CONFIG = {
    "provider": "openai",
    "model": "gpt-test",
    "api_key": "sk-test-not-a-real-key",
}


class CompletingRunner(AgentRunner):
    """Streams a short answer and completes."""

    name = "completing"

    def __init__(self, text: str = "Attention replaces recurrence.") -> None:
        self.text = text
        self.requests: list = []

    async def stream(self, request) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        yield AgentEvent(
            AgentEventType.STARTED, {"provider": request.llm_config.provider}
        )
        for chunk in self.text.split(" "):
            yield AgentEvent(AgentEventType.DELTA, {"text": f"{chunk} "})
        yield AgentEvent(AgentEventType.COMPLETED, {"usage": {"total_tokens": 12}})


class FailingRunner(AgentRunner):
    name = "failing"

    async def stream(self, request) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(
            AgentEventType.FAILED,
            {"code": "search_unavailable", "message": "检索通道不可用"},
        )


def _create_session(client: TestClient, api_prefix: str, token: str) -> str:
    response = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        json={"title": "Reading"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_message_requires_a_transient_llm_config_when_idle(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)

    missing = client.post(
        f"{api_prefix}/sessions/{session_id}/messages",
        headers=auth_headers(token),
        json={"content": "What does the paper claim?"},
    )
    assert missing.status_code == 422
    assert missing.json()["code"] == "validation_error"

    unknown_provider = client.post(
        f"{api_prefix}/sessions/{session_id}/messages",
        headers=auth_headers(token),
        json={
            "content": "hello",
            "llm_config": {**VALID_LLM_CONFIG, "provider": "not-a-provider"},
        },
    )
    assert unknown_provider.status_code == 422
    assert unknown_provider.json()["code"] == "validation_error"
    assert "allowed" in unknown_provider.json()["details"]


def test_message_starts_a_generation_and_writes_entries(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory,
    storage_root,
) -> None:
    runner = CompletingRunner()
    install_agent_runner(
        client,
        session_factory=session_factory,
        storage_root=storage_root,
        runner=runner,
    )
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)

    accepted = client.post(
        f"{api_prefix}/sessions/{session_id}/messages",
        headers=auth_headers(token),
        json={
            "content": "  What does the paper claim?  ",
            "llm_config": VALID_LLM_CONFIG,
        },
    )

    assert accepted.status_code == 202, accepted.text
    body = accepted.json()
    assert body["generation_started"] is True
    assert body["pending"] is None
    assert body["entry"]["payload"]["role"] == "user"
    assert body["entry"]["payload"]["content"] == "What does the paper claim?"

    history = client.get(
        f"{api_prefix}/sessions/{session_id}/entries",
        headers=auth_headers(token),
    ).json()
    assert [item["payload"].get("role") for item in history["items"]] == [
        "user",
        "assistant",
    ]
    assistant = history["items"][1]["payload"]
    assert assistant["stop_reason"] == "completed"
    assert assistant["content"] == "Attention replaces recurrence. "
    assert assistant["model"] == "gpt-test"
    # The LLM key is never persisted into the entry log.
    assert "api_key" not in json.dumps(history)

    assert runner.requests, "the runner must receive the projected turn"
    assert runner.requests[0].messages[0]["role"] == "user"


def test_failed_generation_is_recorded_and_not_reported_as_success(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory,
    storage_root,
) -> None:
    install_agent_runner(
        client,
        session_factory=session_factory,
        storage_root=storage_root,
        runner=FailingRunner(),
    )
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)

    client.post(
        f"{api_prefix}/sessions/{session_id}/messages",
        headers=auth_headers(token),
        json={"content": "summarize", "llm_config": VALID_LLM_CONFIG},
    )

    history = client.get(
        f"{api_prefix}/sessions/{session_id}/entries",
        headers=auth_headers(token),
    ).json()
    assistant = history["items"][-1]["payload"]
    assert assistant["stop_reason"] == "failed"
    assert assistant["error_code"] == "search_unavailable"
    assert assistant["content"] == ""


def test_default_runner_reports_that_the_agent_is_not_wired_yet(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)

    client.post(
        f"{api_prefix}/sessions/{session_id}/messages",
        headers=auth_headers(token),
        json={"content": "hello", "llm_config": VALID_LLM_CONFIG},
    )
    detail = client.get(
        f"{api_prefix}/sessions/{session_id}",
        headers=auth_headers(token),
    ).json()
    history = client.get(
        f"{api_prefix}/sessions/{session_id}/entries",
        headers=auth_headers(token),
    ).json()

    assert detail["pending"] == {"steering": 0, "follow_up": 0}
    assert history["items"][-1]["payload"]["error_code"] == "agent_unavailable"


def test_stop_without_an_active_generation_conflicts(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)

    response = client.post(
        f"{api_prefix}/sessions/{session_id}/stop",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "session_not_generating"


def test_resume_delivers_the_next_queued_message(
    client: TestClient,
    api_prefix: str,
    register_user,
    db_session,
    session_factory,
    storage_root,
) -> None:
    from uuid import UUID

    from app.sessions.domain import Delivery
    from app.sessions.persistence import SessionRepository

    runner = CompletingRunner()
    install_agent_runner(
        client,
        session_factory=session_factory,
        storage_root=storage_root,
        runner=runner,
    )
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)

    repository = SessionRepository(db_session)
    repository.enqueue(
        session_id=UUID(session_id),
        delivery=Delivery.STEERING,
        content="Focus on the encoder.",
    )
    repository.enqueue(
        session_id=UUID(session_id),
        delivery=Delivery.STEERING,
        content="And the decoder.",
    )
    db_session.commit()

    detail = client.get(
        f"{api_prefix}/sessions/{session_id}",
        headers=auth_headers(token),
    ).json()
    assert detail["pending"] == {"steering": 2, "follow_up": 0}
    assert [item["position"] for item in detail["pending_messages"]] == [1, 2]

    no_config = client.post(
        f"{api_prefix}/sessions/{session_id}/resume",
        headers=auth_headers(token),
        json={"llm_config": {**VALID_LLM_CONFIG, "api_key": ""}},
    )
    assert no_config.status_code == 422

    resumed = client.post(
        f"{api_prefix}/sessions/{session_id}/resume",
        headers=auth_headers(token),
        json={"llm_config": VALID_LLM_CONFIG},
    )

    assert resumed.status_code == 202, resumed.text
    body = resumed.json()
    assert body["delivered"]["payload"]["content"] == "Focus on the encoder."
    # The delivered turn reached its safe boundary, so the second steering
    # message was handed over too instead of waiting for another user action.
    assert body["pending"] == {"steering": 0, "follow_up": 0}

    history = client.get(
        f"{api_prefix}/sessions/{session_id}/entries",
        headers=auth_headers(token),
    ).json()
    assert [item["payload"].get("content") for item in history["items"]] == [
        "Focus on the encoder.",
        "Attention replaces recurrence. ",
        "And the decoder.",
        "Attention replaces recurrence. ",
    ]


def test_resume_conflicts_when_the_queue_is_empty(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)

    response = client.post(
        f"{api_prefix}/sessions/{session_id}/resume",
        headers=auth_headers(token),
        json={"llm_config": VALID_LLM_CONFIG},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "pending_message_not_found"


def test_event_stream_replays_buffered_events_with_cursors(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory,
    storage_root,
) -> None:
    install_agent_runner(
        client,
        session_factory=session_factory,
        storage_root=storage_root,
        runner=CompletingRunner(),
    )
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _create_session(client, api_prefix, token)
    client.post(
        f"{api_prefix}/sessions/{session_id}/messages",
        headers=auth_headers(token),
        json={"content": "hello", "llm_config": VALID_LLM_CONFIG},
    )

    with client.stream(
        "GET",
        f"{api_prefix}/sessions/{session_id}/events",
        headers=auth_headers(token),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = list(response.iter_lines())

    events = _parse_events(lines)
    types = [event["event"] for event in events]
    assert types[0] == "generation.started"
    assert "message.delta" in types
    assert "generation.completed" in types
    assert "queue.updated" in types
    assert [int(event["id"]) for event in events] == sorted(
        int(event["id"]) for event in events
    )
    completed = next(
        event for event in events if event["event"] == "generation.completed"
    )
    payload = json.loads(completed["data"])
    assert payload["type"] == "generation.completed"
    assert payload["data"]["stop_reason"] == "completed"
    assert payload["resource_id"] == session_id
    assert completed["id"] == str(payload["sequence"])

    completed_id = completed["id"]
    with client.stream(
        "GET",
        f"{api_prefix}/sessions/{session_id}/events",
        headers=auth_headers(token),
        params={"last_event_id": completed_id},
    ) as response:
        resumed = _parse_events(list(response.iter_lines()))

    # Replaying from the completed event's cursor yields only later events.
    assert all(int(event["id"]) > int(completed_id) for event in resumed)
    assert "generation.completed" not in [event["event"] for event in resumed]


def test_event_stream_is_session_scoped(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    session_id = _create_session(client, api_prefix, owner["access_token"])

    with client.stream(
        "GET",
        f"{api_prefix}/sessions/{session_id}/events",
        headers=auth_headers(stranger["access_token"]),
    ) as response:
        assert response.status_code == 404


def _parse_events(lines: list[str]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in lines:
        if not line:
            if "event" in current:
                events.append(current)
            current = {}
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        current[field.strip()] = value.strip()
    if current.get("event"):
        events.append(current)
    return events
