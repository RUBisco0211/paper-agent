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


def test_list_and_filter_library_entries(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
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
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(client, api_prefix, token, make_pdf(page_count=2))
    paper_id = uploaded.json()["paper"]["id"]

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    )

    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == paper_id
    assert body["metadata_status"] == "unrecognized"
    assert body["pdf"] == {
        "available": True,
        "page_count": 2,
        "byte_size": body["pdf"]["byte_size"],
    }
    assert body["pdf"]["byte_size"] > 0
    assert body["processing"]["status"] == "failed"
    assert body["processing"]["error_code"] == "provider_not_configured"


def test_pdf_endpoint_serves_the_original_file(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    pdf = make_pdf()
    paper_id = _upload(client, api_prefix, token, pdf).json()["paper"]["id"]

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
) -> None:
    token = register_user(email="reader@example.com")["access_token"]

    response = client.get(
        f"{api_prefix}/papers/{UUID(int=0)}",
        headers=auth_headers(token),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "paper_not_found"


def test_ingestion_job_is_scoped_to_the_owning_user(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    uploaded = _upload(client, api_prefix, owner["access_token"], make_pdf())
    job_id = uploaded.json()["ingestion_job"]["id"]
    paper_id = uploaded.json()["paper"]["id"]

    owner_view = client.get(
        f"{api_prefix}/ingestion-jobs/{job_id}",
        headers=auth_headers(owner["access_token"]),
    )
    stranger_view = client.get(
        f"{api_prefix}/ingestion-jobs/{job_id}",
        headers=auth_headers(stranger["access_token"]),
    )

    assert owner_view.status_code == 200
    assert owner_view.json()["paper_id"] == paper_id
    assert stranger_view.status_code == 404
    assert stranger_view.json()["code"] == "ingestion_job_not_found"


def test_retry_skips_verified_stages_and_reports_the_failed_one(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    from app.library.repo import PaperRepository

    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(client, api_prefix, token, make_pdf())
    job_id = UUID(uploaded.json()["ingestion_job"]["id"])
    paper_id = UUID(uploaded.json()["paper"]["id"])

    failed_view = client.get(
        f"{api_prefix}/ingestion-jobs/{job_id}",
        headers=auth_headers(token),
    )
    assert failed_view.json()["status"] == "failed"
    assert failed_view.json()["error_code"] == "provider_not_configured"
    stages = {stage["stage"]: stage for stage in failed_view.json()["stages"]}
    assert stages["metadata"]["status"] == "succeeded"
    assert stages["fulltext"]["status"] == "failed"
    assert stages["fulltext"]["error_code"] == "provider_not_configured"
    assert stages["fulltext"]["error_message"]

    # Pretend local recognition already produced a verifiable artifact.
    user_paper = PaperRepository(db_session).get_user_paper(paper_id)
    assert user_paper is not None and user_paper.paper_id is not None
    PaperRepository(db_session).set_paper_capabilities(
        user_paper.paper_id,
        has_metadata=True,
    )
    db_session.commit()

    retried = client.post(
        f"{api_prefix}/ingestion-jobs/{job_id}/retry",
        headers=auth_headers(token),
    )

    assert retried.status_code == 202, retried.text
    new_job = retried.json()
    assert new_job["id"] != str(job_id)
    new_stages = {stage["stage"]: stage["status"] for stage in new_job["stages"]}
    # The retry only redoes what is still missing, and MinerU is still absent.
    assert new_stages == {
        "metadata": "skipped",
        "fulltext": "failed",
        "chunking": "pending",
        "embedding": "pending",
    }
    assert new_job["status"] == "failed"


def test_retry_conflicts_while_a_job_is_still_active(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    from app.ingestion.domain import STAGE_ORDER
    from app.ingestion.repo import IngestionRepository
    from app.library.repo import PaperRepository

    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(client, api_prefix, token, make_pdf())
    paper_id = UUID(uploaded.json()["paper"]["id"])
    user_paper = PaperRepository(db_session).get_user_paper(paper_id)
    assert user_paper is not None and user_paper.paper_id is not None
    queued = IngestionRepository(db_session).create_job(
        paper_id=user_paper.paper_id,
        stages=STAGE_ORDER,
    )
    db_session.commit()

    response = client.post(
        f"{api_prefix}/ingestion-jobs/{queued.id}/retry",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ingestion_already_running"


def test_retry_conflicts_when_nothing_is_left_to_do(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    from app.ingestion.repo import IngestionRepository
    from app.library.repo import PaperRepository

    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(client, api_prefix, token, make_pdf())
    job_id = UUID(uploaded.json()["ingestion_job"]["id"])
    paper_id = UUID(uploaded.json()["paper"]["id"])

    user_paper = PaperRepository(db_session).get_user_paper(paper_id)
    assert user_paper is not None and user_paper.paper_id is not None
    papers = PaperRepository(db_session)
    papers.set_paper_capabilities(
        user_paper.paper_id,
        has_metadata=True,
        has_fulltext=True,
        has_keyword_index=True,
        has_embedding=True,
    )
    IngestionRepository(db_session).finish_job(
        job_id, error_code="provider_unavailable"
    )
    db_session.commit()

    response = client.post(
        f"{api_prefix}/ingestion-jobs/{job_id}/retry",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ingestion_nothing_to_retry"
