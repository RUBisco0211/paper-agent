from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_headers


def _upload(client: TestClient, api_prefix: str, token: str, pdf: bytes):
    return client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", pdf, "application/pdf")},
    )


def _entry_id(client: TestClient, api_prefix: str, token: str, pdf: bytes) -> str:
    """Upload and return the library entry the finished import produced."""
    response = _upload(client, api_prefix, token, pdf)
    assert response.status_code == 202, response.text
    items = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    return items["items"][0]["id"]


def test_list_and_filter_library_entries(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    _upload(client, api_prefix, token, make_pdf(page_count=1))
    _upload(client, api_prefix, token, make_pdf(page_count=2))

    listed = client.get(f"{api_prefix}/papers", headers=auth_headers(token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [item["title"] for item in body["items"]] == ["paper", "paper"]

    paged = client.get(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        params={"limit": 1, "offset": 1},
    )
    assert paged.json()["total"] == 2
    assert len(paged.json()["items"]) == 1
    assert paged.json()["limit"] == 1

    filtered = client.get(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        params={"q": "nothing-matches"},
    )
    assert filtered.json()["total"] == 0
    assert filtered.json()["items"] == []


def test_paper_detail_exposes_capabilities_and_pdf_info(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = _entry_id(client, api_prefix, token, make_pdf(page_count=2))

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    )

    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == paper_id
    assert body["pdf"] == {
        "available": True,
        "page_count": 2,
        "byte_size": body["pdf"]["byte_size"],
    }
    assert body["pdf"]["byte_size"] > 0
    assert body["run_status"] == "success"


def test_pdf_endpoint_serves_the_original_file(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    completed_imports,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    pdf = make_pdf()
    paper_id = _entry_id(client, api_prefix, token, pdf)

    response = client.get(
        f"{api_prefix}/papers/{paper_id}/pdf",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == pdf


def test_library_requires_authentication(client: TestClient, api_prefix: str) -> None:
    anonymous = client.get(f"{api_prefix}/papers")

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "unauthorized"


def test_unknown_paper_id_returns_not_found(
    client: TestClient,
    api_prefix: str,
    register_user,
    completed_imports,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    response = client.get(
        f"{api_prefix}/papers/{UUID(int=0)}",
        headers=auth_headers(token),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "paper_not_found"
