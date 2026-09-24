from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect

from app.conversation.service import EntryStore
from app.platform.storage import ObjectStorage
from app.sessions.domain import EntryType, MessageRole
from tests.conftest import auth_headers


def _create_session(
    client: TestClient,
    api_prefix: str,
    token: str,
    **payload,
) -> dict:
    response = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_session_lifecycle_and_scope(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    empty = client.get(f"{api_prefix}/sessions", headers=auth_headers(token))
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    created = _create_session(client, api_prefix, token, title="  Reading   list  ")
    assert created["title"] == "Reading list"
    assert created["scope"] == "library"
    assert created["project_id"] is None
    assert created["pending"] == {"steering": 0, "follow_up": 0}
    UUID(created["id"])

    detail = client.get(
        f"{api_prefix}/sessions/{created['id']}",
        headers=auth_headers(token),
    )
    assert detail.status_code == 200
    assert detail.json()["pending_messages"] == []

    renamed = client.patch(
        f"{api_prefix}/sessions/{created['id']}",
        headers=auth_headers(token),
        json={"title": "Retrieval"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Retrieval"

    listed = client.get(f"{api_prefix}/sessions", headers=auth_headers(token))
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == created["id"]

    deleted = client.delete(
        f"{api_prefix}/sessions/{created['id']}",
        headers=auth_headers(token),
    )
    assert deleted.status_code == 204
    missing = client.get(
        f"{api_prefix}/sessions/{created['id']}",
        headers=auth_headers(token),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "session_not_found"


def test_project_sessions_are_listed_separately(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(token),
        json={"name": "Scoped"},
    ).json()
    library_session = _create_session(client, api_prefix, token)
    project_session = _create_session(
        client,
        api_prefix,
        token,
        project_id=project["id"],
    )

    assert project_session["scope"] == "project"
    assert project_session["project_id"] == project["id"]

    library_list = client.get(f"{api_prefix}/sessions", headers=auth_headers(token))
    assert [item["id"] for item in library_list.json()["items"]] == [
        library_session["id"],
    ]

    project_list = client.get(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        params={"scope": "project", "project_id": project["id"]},
    )
    assert [item["id"] for item in project_list.json()["items"]] == [
        project_session["id"],
    ]


def test_sessions_are_isolated_between_users(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    session = _create_session(client, api_prefix, owner["access_token"])

    for method, path, payload in (
        ("get", f"/sessions/{session['id']}", None),
        ("patch", f"/sessions/{session['id']}", {"title": "Stolen"}),
        ("delete", f"/sessions/{session['id']}", None),
        ("get", f"/sessions/{session['id']}/entries", None),
    ):
        response = getattr(client, method)(
            f"{api_prefix}{path}",
            headers=auth_headers(stranger["access_token"]),
            **({"json": payload} if payload else {}),
        )
        assert response.status_code == 404, response.text
        assert response.json()["code"] == "session_not_found"

    stranger_project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(owner["access_token"]),
        json={"name": "Owner project"},
    ).json()
    foreign_project = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(stranger["access_token"]),
        json={"project_id": stranger_project["id"]},
    )
    assert foreign_project.status_code == 404
    assert foreign_project.json()["code"] == "project_not_found"


def test_entry_history_is_append_only_and_pageable(
    client: TestClient,
    api_prefix: str,
    register_user,
    storage: ObjectStorage,
) -> None:
    session_payload = register_user(email="reader@example.com")
    token = session_payload["access_token"]
    user_id = UUID(
        client.get(
            f"{api_prefix}/auth/me",
            headers=auth_headers(token),
        ).json()["id"],
    )
    session = _create_session(client, api_prefix, token)
    session_id = UUID(session["id"])

    store = EntryStore(storage)
    first = store.append_message(
        user_id=user_id,
        session_id=session_id,
        role=MessageRole.USER,
        content="What does the paper claim about attention?",
    )
    second = store.append_message(
        user_id=user_id,
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content="It replaces recurrence with attention.",
        stop_reason="completed",
    )
    store.append(
        user_id=user_id,
        session_id=session_id,
        entry_type=EntryType.MODEL_CHANGE,
        payload={"provider": "openai", "model": "gpt-x"},
    )

    history = client.get(
        f"{api_prefix}/sessions/{session['id']}/entries",
        headers=auth_headers(token),
    )
    assert history.status_code == 200
    items = history.json()["items"]
    assert [item["sequence"] for item in items] == [1, 2, 3]
    assert items[0]["id"] == str(first.id)
    assert items[1]["parent_id"] == str(first.id)
    assert items[1]["payload"]["content"] == "It replaces recurrence with attention."
    assert items[1]["payload"]["stop_reason"] == "completed"
    assert items[2]["type"] == "model_change"
    assert second.parent_id == first.id

    tail = client.get(
        f"{api_prefix}/sessions/{session['id']}/entries",
        headers=auth_headers(token),
        params={"after_sequence": 1, "limit": 1},
    )
    assert [item["sequence"] for item in tail.json()["items"]] == [2]

    assert storage.exists(
        f"sessions/{user_id}/{session['id']}.jsonl",
    )


def test_deleting_a_session_removes_its_entry_log(
    client: TestClient,
    api_prefix: str,
    register_user,
    storage: ObjectStorage,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    user_id = UUID(
        client.get(
            f"{api_prefix}/auth/me",
            headers=auth_headers(token),
        ).json()["id"],
    )
    session = _create_session(client, api_prefix, token)
    session_id = UUID(session["id"])
    storage = storage
    store = EntryStore(storage)
    store.append_message(
        user_id=user_id,
        session_id=session_id,
        role=MessageRole.USER,
        content="hello",
    )
    key = f"sessions/{user_id}/{session_id}.jsonl"
    assert storage.exists(key)

    deleted = client.delete(
        f"{api_prefix}/sessions/{session['id']}",
        headers=auth_headers(token),
    )

    assert deleted.status_code == 204
    assert not storage.exists(key)


def test_deleting_a_project_purges_its_sessions(
    client: TestClient,
    api_prefix: str,
    register_user,
    storage: ObjectStorage,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    user_id = UUID(
        client.get(
            f"{api_prefix}/auth/me",
            headers=auth_headers(token),
        ).json()["id"],
    )
    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(token),
        json={"name": "Temporary"},
    ).json()
    session = _create_session(
        client,
        api_prefix,
        token,
        project_id=project["id"],
    )
    session_id = UUID(session["id"])
    storage = storage
    EntryStore(storage).append_message(
        user_id=user_id,
        session_id=session_id,
        role=MessageRole.USER,
        content="hello",
    )
    key = f"sessions/{user_id}/{session_id}.jsonl"
    assert storage.exists(key)

    deleted = client.delete(
        f"{api_prefix}/projects/{project['id']}",
        headers=auth_headers(token),
    )

    assert deleted.status_code == 204
    assert not storage.exists(key)
    gone = client.get(
        f"{api_prefix}/sessions/{session['id']}",
        headers=auth_headers(token),
    )
    assert gone.status_code == 404


def test_single_paper_session_scope(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
) -> None:
    """单篇文献会话只覆盖那一篇，且不与项目混在一起。"""
    token = register_user(email="reader@example.com")["access_token"]
    uploaded = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", make_pdf(), "application/pdf")},
    ).json()
    paper_id = uploaded["paper"]["id"]

    created = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        json={"paper_id": paper_id, "title": "这篇文献"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["scope"] == "paper"
    assert body["paper_id"] == paper_id
    assert body["project_id"] is None

    # 全局会话列表不含单篇文献会话
    library_list = client.get(
        f"{api_prefix}/sessions", headers=auth_headers(token)
    ).json()
    assert library_list["total"] == 0

    paper_list = client.get(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        params={"scope": "paper"},
    ).json()
    assert paper_list["total"] == 1
    assert paper_list["items"][0]["paper_id"] == paper_id

    filtered = client.get(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        params={"scope": "paper", "paper_id": paper_id},
    ).json()
    assert filtered["total"] == 1


def test_single_paper_session_keeps_scope_in_the_entry_log(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    engine: Engine,
    storage: ObjectStorage,
) -> None:
    """范围通过会话上下文注入，不在数据库里建立会话与文献的关联。"""
    from app.conversation.service import EntryStore
    from app.sessions.domain import EntryType

    token = register_user(email="reader@example.com")["access_token"]
    uploaded = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("attention.pdf", make_pdf(), "application/pdf")},
    ).json()
    paper_id = uploaded["paper"]["id"]

    created = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        json={"paper_id": paper_id},
    ).json()
    user_id = UUID(
        client.get(f"{api_prefix}/auth/me", headers=auth_headers(token)).json()["id"],
    )

    store = EntryStore(storage)
    entries = store.list_entries(user_id=user_id, session_id=UUID(created["id"]))
    assert entries[0].type is EntryType.SESSION_CONTEXT
    assert entries[0].payload["kind"] == "paper"
    assert entries[0].payload["paper_id"] == paper_id

    context = store.session_context(user_id=user_id, session_id=UUID(created["id"]))
    assert context.kind == "paper"
    assert context.paper_id == UUID(paper_id)

    # sessions 表没有指向文献的列
    columns = {column["name"] for column in inspect(engine).get_columns("sessions")}
    assert "user_paper_id" not in columns


def test_single_paper_session_validates_input(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    token = owner["access_token"]
    uploaded = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", make_pdf(), "application/pdf")},
    ).json()
    paper_id = uploaded["paper"]["id"]

    both = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        json={"paper_id": paper_id, "project_id": str(UUID(int=0))},
    )
    assert both.status_code == 422
    assert both.json()["code"] == "validation_error"

    unknown = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        json={"paper_id": str(UUID(int=0))},
    )
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "paper_not_found"

    foreign = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(stranger["access_token"]),
        json={"paper_id": paper_id},
    )
    assert foreign.status_code == 404
