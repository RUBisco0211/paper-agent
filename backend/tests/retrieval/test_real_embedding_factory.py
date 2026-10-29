"""Exercise production factories, replacing only outbound HTTP, not adapters."""

import json
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.library.repo import PaperRepository
from app.literature_support.embedding import build_embedding_adapter
from app.literature_support.embedding import client as embedding_client
from app.platform.config import Settings, settings
from app.retrieval.repo import ChunkRecord, ChunkRepository
from tests.conftest import auth_headers
from tests.retrieval.test_search_api import _index_chunks, _upload


def test_embedding_defaults_to_bge_m3_when_model_is_not_configured(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    assert Settings(_env_file=None).embedding_model == "BAAI/bge-m3"


@pytest.mark.parametrize("internal", [False, True], ids=["public", "agent-internal"])
def test_search_uses_user_key_and_returns_indexed_vectors_when_real_factory_is_wired(
    client, api_prefix, register_user, make_pdf, db_session, monkeypatch, internal,
    completed_imports,
):
    monkeypatch.setattr(settings, "credential_master_key", SecretStr("a" * 64))
    monkeypatch.setattr(settings, "embedding_api_url", "https://embedding.test/v1")
    monkeypatch.setattr(settings, "embedding_api_key", "platform-sentinel")
    monkeypatch.setattr(settings, "agent_internal_key", "a" * 64)
    calls = []
    vector = [1.0] + [0.0] * (settings.embedding_dimensions - 1)

    def handle(request):
        body = json.loads(request.content)
        calls.append((request.headers.get("authorization"), body["model"]))
        return httpx.Response(200, json={"data": [
            {"index": i, "embedding": vector} for i, _ in enumerate(body["input"])
        ]})

    monkeypatch.setattr(embedding_client, "default_http_client_factory", lambda:
                        httpx.Client(transport=httpx.MockTransport(handle)))
    user = register_user(email="real-factory@example.com")
    token = user["access_token"]
    paper_id = _upload(client, api_prefix, token, make_pdf())
    _index_chunks(db_session, user_paper_id=paper_id, contents=["attention mechanism"])
    entry = PaperRepository(db_session).get_user_paper(UUID(paper_id))
    assert entry is not None and entry.paper_id is not None
    adapter = build_embedding_adapter()
    embedded = adapter.embed_documents(["attention mechanism"])
    repository = ChunkRepository(db_session)
    for chunk, result in zip(
        repository.pending_embedding_chunks(entry.paper_id), embedded, strict=True,
    ):
        repository.set_embedding(
            chunk_id=chunk.id, embedding=result, model=adapter.model,
        )
    db_session.commit()
    assert calls == [("Bearer platform-sentinel", settings.embedding_model)]
    saved = client.put(
        f"{api_prefix}/service-credentials/embedding", headers=auth_headers(token),
        json={"kind": "embedding", "fields": {"api_key": "user-sentinel"}},
    )
    assert saved.status_code == 200
    if internal:
        session_id = str(uuid4())
        bound = client.post(
            f"{api_prefix}/session-bindings", headers=auth_headers(token),
            json={"session_id": session_id},
        )
        assert bound.status_code == 201
        response = client.post(
            f"{api_prefix}/internal/search",
            headers={"X-Agent-Internal-Key": "a" * 64},
            json={"session_id": session_id, "user_id": user["user"]["id"],
                  "query": "attention"},
        )
    else:
        response = client.post(f"{api_prefix}/search", headers=auth_headers(token),
                               json={"query": "attention", "scope": "library"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["channels"]["vector"]["status"] == "ok"
    assert body["channels"]["vector"]["result_count"] == 1
    assert body["evidence"][0]["vector_rank"] == 1
    indexed_model = db_session.scalar(select(ChunkRecord.embedding_model))
    assert calls == [("Bearer platform-sentinel", indexed_model),
                     ("Bearer user-sentinel", indexed_model)]


@pytest.mark.parametrize("override", [None, ""])
def test_explicitly_empty_key_never_falls_back_to_platform_when_building_adapter(
    monkeypatch, override,
):
    monkeypatch.setattr(settings, "embedding_api_key", "platform-sentinel")
    adapter = build_embedding_adapter(api_key=override)
    assert not adapter._api_key
