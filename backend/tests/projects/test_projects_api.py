from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.library.persistence import UserPaperRecord
from app.projects.persistence import ProjectPaperRecord
from tests.conftest import auth_headers


def _upload(client: TestClient, api_prefix: str, token: str, pdf: bytes) -> str:
    response = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()["paper"]["id"]


def _create_project(client: TestClient, api_prefix: str, token: str, name: str) -> str:
    response = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(token),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_project_lifecycle(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    empty = client.get(f"{api_prefix}/projects", headers=auth_headers(token))
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    project_id = _create_project(client, api_prefix, token, "  Agent   Reading  ")

    listed = client.get(f"{api_prefix}/projects", headers=auth_headers(token))
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["name"] == "Agent Reading"
    assert listed.json()["items"][0]["paper_count"] == 0

    renamed = client.patch(
        f"{api_prefix}/projects/{project_id}",
        headers=auth_headers(token),
        json={"name": "Retrieval", "description": "RAG reading list"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Retrieval"
    assert renamed.json()["description"] == "RAG reading list"

    cleared = client.patch(
        f"{api_prefix}/projects/{project_id}",
        headers=auth_headers(token),
        json={"description": None},
    )
    assert cleared.json()["description"] is None

    deleted = client.delete(
        f"{api_prefix}/projects/{project_id}",
        headers=auth_headers(token),
    )
    assert deleted.status_code == 204
    missing = client.get(
        f"{api_prefix}/projects/{project_id}",
        headers=auth_headers(token),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "project_not_found"


def test_invalid_project_name_is_rejected(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    blank = client.post(
        f"{api_prefix}/projects",
        headers=auth_headers(token),
        json={"name": "   "},
    )

    assert blank.status_code == 422
    assert blank.json()["code"] == "validation_error"


def test_duplicate_names_are_allowed_but_identity_differs(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    first = _create_project(client, api_prefix, token, "Same")
    second = _create_project(client, api_prefix, token, "Same")

    assert first != second
    listed = client.get(f"{api_prefix}/projects", headers=auth_headers(token)).json()
    assert listed["total"] == 2


def test_adding_library_papers_to_a_project(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    first_paper = _upload(client, api_prefix, token, make_pdf(page_count=1))
    second_paper = _upload(client, api_prefix, token, make_pdf(page_count=2))
    project_id = _create_project(client, api_prefix, token, "Reading")

    added = client.post(
        f"{api_prefix}/projects/{project_id}/papers",
        headers=auth_headers(token),
        json={"paper_ids": [first_paper, second_paper]},
    )
    assert added.status_code == 201, added.text
    assert [item["id"] for item in added.json()["added"]] == [
        first_paper,
        second_paper,
    ]
    assert added.json()["already_present"] == []

    again = client.post(
        f"{api_prefix}/projects/{project_id}/papers",
        headers=auth_headers(token),
        json={"paper_ids": [first_paper]},
    )
    assert again.status_code == 201
    assert again.json()["added"] == []
    assert again.json()["already_present"] == [first_paper]
    assert db_session.scalar(select(func.count(ProjectPaperRecord.id))) == 2

    listed = client.get(
        f"{api_prefix}/projects/{project_id}/papers",
        headers=auth_headers(token),
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert [item["id"] for item in listed.json()["items"]] == [
        first_paper,
        second_paper,
    ]
    assert listed.json()["items"][0]["capabilities"]["has_pdf"] is True

    detail = client.get(
        f"{api_prefix}/projects/{project_id}",
        headers=auth_headers(token),
    )
    assert detail.json()["paper_count"] == 2


def test_project_scope_does_not_leak_between_users(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    owner_token = owner["access_token"]
    stranger_token = stranger["access_token"]

    paper_id = _upload(client, api_prefix, owner_token, make_pdf())
    project_id = _create_project(client, api_prefix, owner_token, "Private")
    client.post(
        f"{api_prefix}/projects/{project_id}/papers",
        headers=auth_headers(owner_token),
        json={"paper_ids": [paper_id]},
    )

    for path in (
        f"{api_prefix}/projects/{project_id}",
        f"{api_prefix}/projects/{project_id}/papers",
    ):
        response = client.get(path, headers=auth_headers(stranger_token))
        assert response.status_code == 404
        assert response.json()["code"] == "project_not_found"

    foreign_write = client.post(
        f"{api_prefix}/projects/{project_id}/papers",
        headers=auth_headers(stranger_token),
        json={"paper_ids": [paper_id]},
    )
    assert foreign_write.status_code == 404

    foreign_delete = client.delete(
        f"{api_prefix}/projects/{project_id}",
        headers=auth_headers(stranger_token),
    )
    assert foreign_delete.status_code == 404


def test_cannot_add_another_users_paper_to_a_project(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    foreign_paper = _upload(client, api_prefix, owner["access_token"], make_pdf())
    project_id = _create_project(client, api_prefix, stranger["access_token"], "Mine")

    response = client.post(
        f"{api_prefix}/projects/{project_id}/papers",
        headers=auth_headers(stranger["access_token"]),
        json={"paper_ids": [foreign_paper]},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "paper_not_found"


def test_deleting_a_project_keeps_library_entries(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = _upload(client, api_prefix, token, make_pdf())
    project_id = _create_project(client, api_prefix, token, "Temporary")
    client.post(
        f"{api_prefix}/projects/{project_id}/papers",
        headers=auth_headers(token),
        json={"paper_ids": [paper_id]},
    )

    deleted = client.delete(
        f"{api_prefix}/projects/{project_id}",
        headers=auth_headers(token),
    )

    assert deleted.status_code == 204
    library = client.get(f"{api_prefix}/papers", headers=auth_headers(token))
    assert library.json()["total"] == 1
    assert library.json()["items"][0]["id"] == paper_id
    assert db_session.scalar(select(func.count(UserPaperRecord.id))) == 1
    assert db_session.scalar(select(func.count(ProjectPaperRecord.id))) == 0
