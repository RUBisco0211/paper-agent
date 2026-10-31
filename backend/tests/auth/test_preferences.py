from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_preferences_start_empty_and_keep_the_saved_notification_default(
    client: TestClient, api_prefix: str, register_user
):
    owner = register_user(email="preferences@example.com")
    headers = auth_headers(owner["access_token"])

    initial = client.get(f"{api_prefix}/auth/preferences", headers=headers)
    assert initial.status_code == 200
    assert initial.json() == {"timezone": None, "notify_email_default": False}

    saved = client.patch(
        f"{api_prefix}/auth/preferences",
        headers=headers,
        json={"notify_email_default": True},
    )
    assert saved.status_code == 200
    assert saved.json()["notify_email_default"] is True

    # 时区由它自己的接口写，偏好读取时一并返回。
    assert (
        client.patch(
            f"{api_prefix}/auth/timezone",
            headers=headers,
            json={"timezone": "Europe/Berlin"},
        ).status_code
        == 200
    )
    after = client.get(f"{api_prefix}/auth/preferences", headers=headers)
    assert after.json() == {"timezone": "Europe/Berlin", "notify_email_default": True}


def test_preferences_are_private_to_each_account(
    client: TestClient, api_prefix: str, register_user
):
    first = register_user(email="prefs-first@example.com")
    second = register_user(email="prefs-second@example.com")
    client.patch(
        f"{api_prefix}/auth/preferences",
        headers=auth_headers(first["access_token"]),
        json={"notify_email_default": True},
    )

    other = client.get(
        f"{api_prefix}/auth/preferences",
        headers=auth_headers(second["access_token"]),
    )

    assert other.json() == {"timezone": None, "notify_email_default": False}

def test_preferences_are_never_cached_by_the_browser(
    client: TestClient, api_prefix: str, register_user
):
    owner = register_user(email="prefs-cache@example.com")

    response = client.get(
        f"{api_prefix}/auth/preferences",
        headers=auth_headers(owner["access_token"]),
    )

    assert response.headers["cache-control"] == "no-store"
