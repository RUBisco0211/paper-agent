from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.library.repo import PaperRepository
from app.platform.config import settings
from app.retrieval.depends import get_search_embedding_factory
from app.retrieval.domain import ChunkDraft
from app.retrieval.repo import ChunkRepository
from tests.conftest import auth_headers


def _upload(client: TestClient, api_prefix: str, token: str, pdf: bytes) -> str:
    response = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()["paper"]["id"]


def _index_chunks(
    db_session: Session,
    *,
    user_paper_id: str,
    contents: list[str],
    embedding: list[float] | None = None,
    indexes: list[int] | None = None,
) -> None:
    """Attach chunks to an uploaded paper, as the chunking stage would."""
    user_paper = PaperRepository(db_session).get_user_paper(UUID(user_paper_id))
    assert user_paper is not None and user_paper.paper_id is not None
    repository = ChunkRepository(db_session)
    repository.replace_chunks(
        paper_id=user_paper.paper_id,
        drafts=[
            ChunkDraft(
                chunk_index=(indexes or list(range(len(contents))))[position],
                content=content,
                title_path=f"Section {position}",
                page_start=position + 1,
                page_end=position + 1,
                block_ids=[f"block-{position}"],
            )
            for position, content in enumerate(contents)
        ],
    )
    if embedding is not None:
        for chunk in repository.pending_embedding_chunks(user_paper.paper_id):
            repository.set_embedding(
                chunk_id=chunk.id,
                embedding=embedding,
                model=settings.embedding_model,
            )
    db_session.commit()


class FakeEmbeddingAdapter:
    """实现 EmbeddingAdapter：记录查询文本，返回固定向量。"""

    name = "fake"
    model = settings.embedding_model
    dimensions = settings.embedding_dimensions
    is_configured = True

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector
        self.queries: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.vector for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self.vector


def test_keyword_search_returns_evidence_with_stable_ids(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = _upload(client, api_prefix, token, make_pdf())
    _index_chunks(
        db_session,
        user_paper_id=paper_id,
        contents=[
            "The transformer architecture relies on multi head attention.",
            "Unrelated appendix material about dataset licenses.",
        ],
    )

    response = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "multi head attention", "scope": "library"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "library"
    # This user saved no embedding key, so only keyword recall ran.
    assert body["status"] == "degraded"
    assert body["channels"]["keyword"]["status"] == "ok"
    assert body["channels"]["keyword"]["result_count"] == 1
    assert body["channels"]["vector"]["status"] == "unavailable"

    evidence = body["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["paper_id"] == paper_id
    assert evidence[0]["page_start"] == 1
    assert evidence[0]["page_end"] == 1
    assert evidence[0]["keyword_rank"] == 1
    assert evidence[0]["vector_rank"] is None
    assert "attention" in evidence[0]["snippet"]
    UUID(evidence[0]["chunk_ids"][0])


def test_search_does_not_leak_other_users_papers(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    owner = register_user(email="owner@example.com")
    stranger = register_user(email="stranger@example.com")
    owner_paper = _upload(client, api_prefix, owner["access_token"], make_pdf())
    _index_chunks(
        db_session,
        user_paper_id=owner_paper,
        contents=["Confidential unpublished results about multi head attention."],
    )

    response = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(stranger["access_token"]),
        json={"query": "multi head attention"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evidence"] == []
    assert body["channels"]["keyword"]["detail"] == "no full text in scope"


def test_paper_scope_restricts_search_to_selected_entries(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    first = _upload(client, api_prefix, token, make_pdf(page_count=1))
    second = _upload(client, api_prefix, token, make_pdf(page_count=2))
    _index_chunks(db_session, user_paper_id=first, contents=["alpha attention study"])
    _index_chunks(db_session, user_paper_id=second, contents=["beta attention study"])

    scoped = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "attention", "scope": "paper", "paper_ids": [second]},
    )
    assert scoped.status_code == 200
    assert [item["paper_id"] for item in scoped.json()["evidence"]] == [second]

    foreign = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={
            "query": "attention",
            "scope": "paper",
            "paper_ids": [str(UUID(int=0))],
        },
    )
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "paper_not_found"


def test_project_scope_only_covers_project_papers(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    inside = _upload(client, api_prefix, token, make_pdf(page_count=1))
    outside = _upload(client, api_prefix, token, make_pdf(page_count=2))
    _index_chunks(db_session, user_paper_id=inside, contents=["inside attention note"])
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

    scoped = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={
            "query": "attention",
            "scope": "project",
            "project_id": project["id"],
        },
    )
    assert scoped.status_code == 200
    assert [item["paper_id"] for item in scoped.json()["evidence"]] == [inside]

    unknown = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={
            "query": "attention",
            "scope": "project",
            "project_id": str(UUID(int=0)),
        },
    )
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "project_not_found"


def test_hybrid_search_fuses_keyword_and_vector_channels(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = _upload(client, api_prefix, token, make_pdf())
    vector = [0.01] * settings.embedding_dimensions
    _index_chunks(
        db_session,
        user_paper_id=paper_id,
        contents=[
            "multi head attention improves translation quality",
            "a purely semantic neighbour without shared vocabulary",
        ],
        # Non-adjacent chunks stay separate pieces of evidence.
        indexes=[0, 5],
        embedding=vector,
    )
    fake = FakeEmbeddingAdapter(vector)
    client.app.dependency_overrides[get_search_embedding_factory] = (
        lambda: (lambda _user_id: fake)
    )

    response = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "translation quality", "limit": 5},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["channels"]["keyword"]["status"] == "ok"
    assert body["channels"]["vector"]["status"] == "ok"
    assert fake.queries == ["translation quality"]

    assert len(body["evidence"]) == 2
    top = body["evidence"][0]
    # The chunk hit by both channels wins the RRF fusion.
    assert "multi head attention" in top["snippet"]
    assert top["keyword_rank"] is not None
    assert top["vector_rank"] is not None


def test_search_requires_authentication(client: TestClient, api_prefix: str) -> None:
    response = client.post(f"{api_prefix}/search", json={"query": "attention"})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_reindexing_chunks_is_idempotent(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
) -> None:
    token = register_user(email="reader@example.com")["access_token"]
    paper_id = _upload(client, api_prefix, token, make_pdf())

    _index_chunks(db_session, user_paper_id=paper_id, contents=["first version"])
    _index_chunks(db_session, user_paper_id=paper_id, contents=["second version"])

    user_paper = PaperRepository(db_session).get_user_paper(UUID(paper_id))
    assert user_paper is not None and user_paper.paper_id is not None
    repository = ChunkRepository(db_session)
    assert repository.count_chunks(user_paper.paper_id) == 1

    response = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "second"},
    )
    assert len(response.json()["evidence"]) == 1
    assert "second version" in response.json()["evidence"][0]["snippet"]
