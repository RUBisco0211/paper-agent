from uuid import UUID

from fastapi.testclient import TestClient

from app.evidence.citations import build_citation_id
from app.retrieval.domain import Evidence
from app.sessions.repo import SessionRepository
from app.sessions.service import CitationService
from tests.conftest import auth_headers


def _session(client: TestClient, api_prefix: str, token: str) -> str:
    response = client.post(
        f"{api_prefix}/sessions",
        headers=auth_headers(token),
        json={},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_citation_round_trip_and_ownership(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    token = owner["access_token"]

    uploaded = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", make_pdf(), "application/pdf")},
    ).json()
    paper_id = UUID(uploaded["paper"]["id"])
    session_id = _session(client, api_prefix, token)

    from app.library.repo import PaperRepository
    from app.retrieval.domain import ChunkDraft
    from app.retrieval.repo import ChunkRepository

    user_paper = PaperRepository(db_session).get_user_paper(paper_id)
    assert user_paper is not None and user_paper.paper_id is not None
    chunks = ChunkRepository(db_session)
    chunks.replace_chunks(
        paper_id=user_paper.paper_id,
        drafts=[ChunkDraft(chunk_index=0, content="attention is all you need")],
    )
    db_session.commit()
    chunk = chunks.pending_embedding_chunks(user_paper.paper_id)[0]

    service = CitationService(SessionRepository(db_session))
    recorded = service.record_evidence(
        session_id=UUID(session_id),
        evidence=[
            Evidence(
                paper_id=paper_id,
                chunk_ids=[chunk.id],
                title_path="3 Model",
                snippet="attention is all you need",
                page_start=2,
                page_end=2,
                score=0.5,
                chunk_index=0,
            ),
        ],
    )
    citation_id = recorded[0].citation_id
    assert citation_id == build_citation_id([chunk.id])

    resolved = client.get(
        f"{api_prefix}/sessions/{session_id}/citations/{citation_id}",
        headers=auth_headers(token),
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["citation_id"] == citation_id
    assert body["paper_id"] == str(paper_id)
    assert body["page_start"] == 2
    assert body["page_end"] == 2
    assert body["title_path"] == "3 Model"
    assert body["snippet"] == "attention is all you need"
    assert body["chunk_ids"] == [str(chunk.id)]

    # The same evidence is idempotent inside one session.
    again = service.record_evidence(
        session_id=UUID(session_id),
        evidence=[
            Evidence(
                paper_id=paper_id,
                chunk_ids=[chunk.id],
                title_path=None,
                snippet="attention is all you need",
                page_start=2,
                page_end=2,
                score=0.9,
                chunk_index=0,
            ),
        ],
    )
    assert again[0].citation_id == citation_id
    assert SessionRepository(db_session).get_citation(
        session_id=UUID(session_id),
        citation_id=citation_id,
    )

    foreign = client.get(
        f"{api_prefix}/sessions/{session_id}/citations/{citation_id}",
        headers=auth_headers(stranger["access_token"]),
    )
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "session_not_found"


def test_unknown_citation_is_rejected(
    client: TestClient,
    api_prefix: str,
    register_user,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    session_id = _session(client, api_prefix, token)

    response = client.get(
        f"{api_prefix}/sessions/{session_id}/citations/cit_deadbeef1234",
        headers=auth_headers(token),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "citation_not_found"
