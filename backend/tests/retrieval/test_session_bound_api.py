from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.library.repo import UserPaperRecord
from app.platform.config import settings
from app.retrieval.repo import ChunkRecord
from app.sessions.repo import SessionBindingRepository
from tests.conftest import auth_headers
from tests.retrieval.test_search_api import _index_chunks, _upload


def test_binding_list_contains_only_the_current_users_sessions_when_owners_differ(
    client: TestClient, api_prefix: str, register_user
) -> None:
    owner = register_user(email="binding-list-owner@example.com")
    stranger = register_user(email="binding-list-stranger@example.com")
    session_id = str(uuid4())
    created = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    assert created.status_code == 201

    own = client.get(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
    )
    foreign = client.get(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(stranger["access_token"]),
    )

    assert own.status_code == 200
    assert [item["session_id"] for item in own.json()["items"]] == [session_id]
    assert foreign.status_code == 200
    assert foreign.json()["items"] == []


def test_registered_citation_is_visible_only_to_the_bound_owner_when_queried(
    client: TestClient, api_prefix: str, register_user, make_pdf, db_session
) -> None:
    owner = register_user(email="citation-owner@example.com")
    stranger = register_user(email="citation-stranger@example.com")
    paper_id = _upload(
        client, api_prefix, owner["access_token"], make_pdf(page_count=1)
    )
    session_id = str(uuid4())
    created = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    assert created.status_code == 201
    SessionBindingRepository(db_session).add_citation(
        session_id=UUID(created.json()["session_id"]),
        citation_id="cit_registered",
        user_paper_id=UUID(paper_id),
        chunk_ids=[],
        title_path="Introduction",
        snippet="Evidence from the paper",
        page_start=1,
        page_end=1,
    )
    db_session.commit()
    path = f"{api_prefix}/session-bindings/{session_id}/citations/cit_registered"

    own = client.get(path, headers=auth_headers(owner["access_token"]))
    foreign = client.get(path, headers=auth_headers(stranger["access_token"]))
    missing = client.get(
        f"{api_prefix}/session-bindings/{session_id}/citations/cit_missing",
        headers=auth_headers(owner["access_token"]),
    )

    assert own.status_code == 200
    assert own.json()["paper_id"] == paper_id
    assert own.json()["snippet"] == "Evidence from the paper"
    assert foreign.status_code == 404
    assert missing.status_code == 404


def test_session_binding_rejects_deletion_when_user_does_not_own_it(
    client: TestClient, api_prefix: str, register_user
) -> None:
    owner = register_user(email="delete-owner@example.com")
    stranger = register_user(email="delete-stranger@example.com")
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )

    response = client.delete(
        f"{api_prefix}/session-bindings/{session_id}",
        headers=auth_headers(stranger["access_token"]),
    )

    assert response.status_code == 404
    own = client.get(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
    )
    assert [item["session_id"] for item in own.json()["items"]] == [session_id]


def test_session_binding_deletion_removes_registered_citations_when_owner_deletes_it(
    client: TestClient, api_prefix: str, register_user, make_pdf, db_session
) -> None:
    owner = register_user(email="delete-citation-owner@example.com")
    paper_id = _upload(
        client, api_prefix, owner["access_token"], make_pdf(page_count=1)
    )
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    SessionBindingRepository(db_session).add_citation(
        session_id=UUID(session_id),
        citation_id="cit_delete_me",
        user_paper_id=UUID(paper_id),
        chunk_ids=[],
        title_path=None,
        snippet="Saved excerpt",
        page_start=1,
        page_end=1,
    )
    db_session.commit()

    response = client.delete(
        f"{api_prefix}/session-bindings/{session_id}",
        headers=auth_headers(owner["access_token"]),
    )

    assert response.status_code == 204
    assert (
        SessionBindingRepository(db_session).get_citation(
            UUID(session_id), "cit_delete_me"
        )
        is None
    )


def test_session_binding_deletion_returns_not_found_when_already_removed(
    client: TestClient, api_prefix: str, register_user
) -> None:
    owner = register_user(email="delete-repeat-owner@example.com")
    session_id = str(uuid4())
    client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    client.delete(
        f"{api_prefix}/session-bindings/{session_id}",
        headers=auth_headers(owner["access_token"]),
    )

    response = client.delete(
        f"{api_prefix}/session-bindings/{session_id}",
        headers=auth_headers(owner["access_token"]),
    )

    assert response.status_code == 404


def test_session_binding_rejects_another_users_project_when_created(
    client: TestClient, api_prefix: str, register_user
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(owner["access_token"]),
        json={"name": "Private project"},
    ).json()
    session_id = str(uuid4())
    created = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id, "project_id": project["id"]},
    )

    response = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(stranger["access_token"]),
        json={"session_id": str(uuid4()), "project_id": project["id"]},
    )

    assert created.status_code == 201
    assert response.status_code == 404


def test_internal_search_rejects_unbound_session_and_invalid_secret(
    client: TestClient, api_prefix: str, register_user, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    user = register_user()
    user_id = user["user"]["id"]
    session_id = str(uuid4())
    payload = {"user_id": user_id, "session_id": session_id, "query": "attention"}

    invalid = client.post(
        f"{api_prefix}/internal/search",
        headers={"X-Agent-Internal-Key": "wrong"},
        json=payload,
    )
    unbound = client.post(
        f"{api_prefix}/internal/search",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json=payload,
    )

    assert invalid.status_code == 401
    assert unbound.status_code == 404


def test_session_binding_cannot_change_scope_after_creation(
    client: TestClient, api_prefix: str, register_user
) -> None:
    token = register_user()["access_token"]
    session_id = str(uuid4())
    first = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(token),
        json={"session_id": session_id},
    )
    second = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(token),
        json={"session_id": session_id},
    )

    assert first.status_code == 201
    assert first.json()["scope"] == "library"
    assert second.status_code == 409


def test_internal_search_rejects_another_user_on_a_bound_session(
    client: TestClient, api_prefix: str, register_user, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    session_id = str(uuid4())
    bound = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(owner["access_token"]),
        json={"session_id": session_id},
    )
    assert bound.status_code == 201

    response = client.post(
        f"{api_prefix}/internal/search",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json={
            "user_id": stranger["user"]["id"],
            "session_id": session_id,
            "query": "attention",
        },
    )

    assert response.status_code == 404


def test_internal_search_uses_bound_project_and_registers_retrievable_citation(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    user = register_user()
    token = user["access_token"]
    inside = _upload(client, api_prefix, token, make_pdf(page_count=1))
    outside = _upload(client, api_prefix, token, make_pdf(page_count=2))
    _index_chunks(db_session, user_paper_id=inside, contents=["inside attention note"])
    paper_id = db_session.get(UserPaperRecord, UUID(inside)).paper_id
    indexed_chunk = db_session.query(ChunkRecord).filter_by(paper_id=paper_id).one()
    indexed_chunk.chunk_metadata = {
        "artifact_manifest_key": "mineru/example/manifest.json",
        "source_ranges": [{"block_id": 0, "char_start": 0, "char_end": 21}],
    }
    db_session.commit()
    _index_chunks(
        db_session, user_paper_id=outside, contents=["outside attention note"]
    )
    project = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(token),
        json={"name": "Scoped"},
    ).json()
    client.post(
        f"{api_prefix}/projects/{project['id']}/papers",
        headers=auth_headers(token),
        json={"paper_ids": [inside]},
    )
    session_id = str(uuid4())
    bound = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(token),
        json={"session_id": session_id, "project_id": project["id"]},
    )
    assert bound.status_code == 201, bound.text

    response = client.post(
        f"{api_prefix}/internal/search",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "query": "attention",
            "project_id": str(uuid4()),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "project"
    assert [item["paper_id"] for item in body["evidence"]] == [inside]
    assert body["evidence"][0]["citation_id"].startswith("cit_")
    excerpt = client.get(
        f"{api_prefix}/internal/excerpt",
        headers={"X-Agent-Internal-Key": "a" * 64},
        params={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "citation_id": body["evidence"][0]["citation_id"],
        },
    )
    assert excerpt.status_code == 200
    assert excerpt.json()["paper_id"] == inside
    assert excerpt.json()["page_start"] == 1
    assert (
        excerpt.json()["source_locations"][0]["chunk_id"]
        == body["evidence"][0]["chunk_ids"][0]
    )
    assert excerpt.json()["source_locations"][0]["source_ranges"][0]["char_end"] == 21
    db_session.delete(indexed_chunk)
    db_session.commit()
    after_reindex = client.get(
        f"{api_prefix}/internal/excerpt",
        headers={"X-Agent-Internal-Key": "a" * 64},
        params={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "citation_id": body["evidence"][0]["citation_id"],
        },
    )
    assert (
        after_reindex.json()["source_locations"] == excerpt.json()["source_locations"]
    )


def test_internal_search_covers_all_owned_papers_when_session_is_global(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    user = register_user()
    token = user["access_token"]
    first = _upload(client, api_prefix, token, make_pdf(page_count=1))
    second = _upload(client, api_prefix, token, make_pdf(page_count=2))
    _index_chunks(db_session, user_paper_id=first, contents=["attention alpha"])
    _index_chunks(db_session, user_paper_id=second, contents=["attention beta"])
    session_id = str(uuid4())
    bound = client.post(
        f"{api_prefix}/session-bindings",
        headers=auth_headers(token),
        json={"session_id": session_id},
    )
    assert bound.status_code == 201

    response = client.post(
        f"{api_prefix}/internal/search",
        headers={"X-Agent-Internal-Key": "a" * 64},
        json={
            "user_id": user["user"]["id"],
            "session_id": session_id,
            "query": "attention",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["scope"] == "library"
    assert {item["paper_id"] for item in response.json()["evidence"]} == {
        first,
        second,
    }
