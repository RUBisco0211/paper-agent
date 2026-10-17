"""Business result events authorize real run bindings before the mail adapter."""

from uuid import UUID, uuid4

import pytest

from app.auth.repo import UserRecord
from app.platform.config import settings
from app.schedules.repo import ScheduleBindingRepository
from tests.conftest import auth_headers


@pytest.fixture
def result_event(client, register_user, monkeypatch):
    monkeypatch.setattr(settings, "agent_internal_key", "test-internal-key")
    owner = register_user()
    schedule_id, session_id = uuid4().hex, uuid4().hex
    response = client.post(
        "/v1/schedule-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"schedule_id": schedule_id, "notify_email": True},
    )
    assert response.status_code == 201
    sent = []

    # Observe the external mail adapter, not schedule/session database queries.
    def enqueue(repository, **message):
        sent.append(message)

    monkeypatch.setattr(ScheduleBindingRepository, "enqueue_result", enqueue)
    body = {
        "user_id": owner["user"]["id"],
        "schedule_id": schedule_id,
        "session_id": session_id,
        "name": "Daily review",
        "status": "success",
        "markdown": "# Final answer\n\n" + "complete result " * 1000,
    }
    return body, sent, {"X-Agent-Internal-Key": "test-internal-key"}, owner


def test_schedule_email_contains_entire_answer_and_run_link_when_owner_is_verified(
    client, result_event
):
    body, sent, headers, owner = result_event
    response = client.post("/v1/internal/schedule-results", json=body, headers=headers)
    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0]["recipient"] == owner["user"]["email"]
    assert "complete result " * 1000 in sent[0]["text_body"]
    assert (
        f"/scheduled/{body['schedule_id']}/runs/{body['session_id']}"
        in sent[0]["text_body"]
    )
    assert settings.public_app_url.rstrip("/") in sent[0]["text_body"]


def test_schedule_email_uses_run_dedupe_key_when_result_event_is_repeated(
    client, result_event
):
    body, sent, headers, _ = result_event
    for _ in range(2):
        assert (
            client.post(
                "/v1/internal/schedule-results", json=body, headers=headers
            ).status_code
            == 200
        )
    assert sent[0]["dedupe_key"] == sent[1]["dedupe_key"]
    assert (
        sent[0]["dedupe_key"]
        == f"schedule-result:{body['schedule_id']}:{body['session_id']}"
    )
    body["session_id"] = uuid4().hex
    assert (
        client.post(
            "/v1/internal/schedule-results", json=body, headers=headers
        ).status_code
        == 200
    )
    assert sent[2]["dedupe_key"] != sent[0]["dedupe_key"]


def test_schedule_email_excludes_partial_markdown_when_event_reports_failure(
    client, result_event
):
    body, sent, headers, _ = result_event
    body.update(
        status="failed",
        error="模型额度不足，请检查额度后重新运行。",
        markdown="private partial",
    )
    assert (
        client.post(
            "/v1/internal/schedule-results", json=body, headers=headers
        ).status_code
        == 200
    )
    assert "private partial" not in sent[0]["html_body"] + sent[0]["text_body"]
    assert "检查额度" in sent[0]["text_body"]


def test_schedule_email_does_not_enqueue_when_owner_email_is_unverified(
    client, db_session, result_event
):
    body, sent, headers, _ = result_event
    owner = db_session.get(UserRecord, UUID(body["user_id"]))
    owner.email_verified_at = None
    db_session.commit()
    assert (
        client.post(
            "/v1/internal/schedule-results", json=body, headers=headers
        ).status_code
        == 200
    )
    assert sent == []


def test_schedule_email_does_not_enqueue_when_owner_has_disabled_notifications(
    client, result_event
):
    body, sent, headers, owner = result_event
    assert (
        client.patch(
            f"/v1/schedules/{body['schedule_id']}",
            headers=auth_headers(owner["access_token"]),
            json={"notify_email": False},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/internal/schedule-results", json=body, headers=headers
        ).status_code
        == 200
    )
    assert sent == []


def test_schedule_result_rejects_event_when_schedule_has_another_owner(
    client, register_user, result_event
):
    body, sent, headers, _ = result_event
    other = register_user(email="other-result-owner@example.com")
    body["user_id"] = other["user"]["id"]
    assert (
        client.post(
            "/v1/internal/schedule-results", json=body, headers=headers
        ).status_code
        == 404
    )
    assert sent == []


def test_schedule_result_rejects_event_when_run_is_bound_to_another_task(
    client, result_event
):
    body, sent, headers, owner = result_event
    session = client.post(
        "/v1/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": body["session_id"]},
    )
    assert session.status_code == 201
    assert (
        client.post(
            "/v1/internal/schedule-results", json=body, headers=headers
        ).status_code
        == 409
    )
    assert sent == []


def test_schedule_result_exposes_submission_failure_when_mail_adapter_raises(
    client, result_event, monkeypatch
):
    body, _, headers, _ = result_event

    def fail(repository, **message):
        raise RuntimeError("mail submission failed")

    monkeypatch.setattr(ScheduleBindingRepository, "enqueue_result", fail)
    with pytest.raises(RuntimeError, match="mail submission failed"):
        client.post("/v1/internal/schedule-results", json=body, headers=headers)
