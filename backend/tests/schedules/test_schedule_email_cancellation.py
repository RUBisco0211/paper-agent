"""Cancellation shares the binding transaction and uses a schedule-scoped key."""

from uuid import uuid4

import pytest

from tests.conftest import auth_headers


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_schedule_passes_cancellation_prefix_when_owner_disables_or_deletes(
    client,
    register_user,
    monkeypatch,
    action,
):
    from app.platform import mail

    owner = register_user()
    headers = auth_headers(owner["access_token"])
    schedule_id = uuid4().hex
    assert (
        client.post(
            "/v1/schedule-bindings",
            headers=headers,
            json={
                "schedule_id": schedule_id,
                "notify_email": True,
            },
        ).status_code
        == 201
    )
    prefixes = []
    cancel = mail.cancel_email

    def observed_cancel(session, *, dedupe_prefix):
        prefixes.append(dedupe_prefix)
        return cancel(session, dedupe_prefix=dedupe_prefix)

    monkeypatch.setattr(mail, "cancel_email", observed_cancel)
    if action == "disable":
        response = client.patch(
            f"/v1/schedules/{schedule_id}",
            headers=headers,
            json={"notify_email": False},
        )
        assert response.status_code == 200
    else:
        assert (
            client.delete(
                f"/v1/schedule-bindings/{schedule_id}", headers=headers
            ).status_code
            == 204
        )
    assert prefixes == [f"schedule-result:{schedule_id}:"]


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_schedule_preserves_binding_when_mail_cancellation_fails(
    client,
    register_user,
    monkeypatch,
    action,
):
    from app.platform import mail

    owner = register_user()
    headers = auth_headers(owner["access_token"])
    schedule_id = uuid4().hex
    assert (
        client.post(
            "/v1/schedule-bindings",
            headers=headers,
            json={
                "schedule_id": schedule_id,
                "notify_email": True,
            },
        ).status_code
        == 201
    )

    def failure(session, *, dedupe_prefix):
        raise RuntimeError("cancel failed")

    monkeypatch.setattr(mail, "cancel_email", failure)
    with pytest.raises(RuntimeError, match="cancel failed"):
        if action == "disable":
            client.patch(
                f"/v1/schedules/{schedule_id}",
                headers=headers,
                json={"notify_email": False},
            )
        else:
            client.delete(f"/v1/schedule-bindings/{schedule_id}", headers=headers)
    bindings = client.get("/v1/schedule-bindings", headers=headers).json()
    assert bindings == [
        {"schedule_id": schedule_id, "project_id": None, "notify_email": True}
    ]
