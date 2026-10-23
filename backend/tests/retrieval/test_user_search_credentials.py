"""Search embeddings are paid by the user whose query triggers them."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.library.repo import PaperRepository
from app.platform.config import settings
from app.retrieval.domain import ChunkDraft
from app.retrieval.repo import ChunkRepository
from tests.conftest import auth_headers

KEY = "sk-user-search-key"


@pytest.fixture(autouse=True)
def master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))


def _upload(client: TestClient, api_prefix: str, token: str, pdf: bytes) -> str:
    response = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("paper.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()["paper"]["id"]


def _index_chunks(db_session: Session, *, user_paper_id: str, contents: list[str]) -> None:
    user_paper = PaperRepository(db_session).get_user_paper(UUID(user_paper_id))
    assert user_paper is not None and user_paper.paper_id is not None
    ChunkRepository(db_session).replace_chunks(
        paper_id=user_paper.paper_id,
        drafts=[
            ChunkDraft(
                chunk_index=position,
                content=content,
                title_path="Section",
                page_start=1,
                page_end=1,
                block_ids=[f"block-{position}"],
            )
            for position, content in enumerate(contents)
        ],
    )
    db_session.commit()


def test_search_uses_the_users_own_key_and_the_indexed_model(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str | None, str]] = []

    class Stub:
        name = "stub"
        model = settings.embedding_model
        dimensions = settings.embedding_dimensions
        is_configured = True

        def embed_query(self, text: str) -> list[float]:
            return [0.1] * self.dimensions

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("search must not embed documents")

    from app.retrieval import depends as retrieval_depends

    def fake_build(api_key: str | None):
        seen.append((api_key, settings.embedding_model))
        return Stub()

    monkeypatch.setattr(retrieval_depends, "_build_adapter", fake_build)

    token = register_user(email="byok@example.com")["access_token"]
    client.put(
        f"{api_prefix}/service-credentials/embedding",
        headers=auth_headers(token),
        json={"kind": "embedding", "fields": {"api_key": KEY}},
    )
    paper_id = _upload(client, api_prefix, token, make_pdf())
    _index_chunks(db_session, user_paper_id=paper_id, contents=["attention is all you need"])

    response = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "attention", "scope": "library"},
    )

    assert response.status_code == 200, response.text
    assert seen == [(KEY, settings.embedding_model)]


def test_search_falls_back_to_keyword_only_when_the_user_saved_no_key(
    client: TestClient,
    api_prefix: str,
    register_user,
    make_pdf,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.retrieval import depends as retrieval_depends

    def explode(api_key: str | None):
        raise AssertionError("no adapter may be built without a user key")

    monkeypatch.setattr(retrieval_depends, "_build_adapter", explode)

    token = register_user(email="no-byok@example.com")["access_token"]
    paper_id = _upload(client, api_prefix, token, make_pdf())
    _index_chunks(db_session, user_paper_id=paper_id, contents=["attention is all you need"])

    response = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "attention", "scope": "library"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["channels"]["keyword"]["status"] == "ok"
    assert body["channels"]["vector"]["status"] == "unavailable"
    assert body["channels"]["vector"]["detail"] == "no embedding api key"
    assert body["evidence"]
