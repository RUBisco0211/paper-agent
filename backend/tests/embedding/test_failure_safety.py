"""Upstream error bodies must never become public errors, rows or logs."""

import logging
from uuid import UUID

import httpx
import pytest

from app.literature_support.embedding import OpenAICompatibleEmbeddingAdapter
from app.literature_support.embedding.base import EmbeddingProfile
from app.literature_support.scholar.metadata import MetadataResolver
from app.platform.config import settings
from app.platform.errors import AppError
from app.processing.repo import IngestionRepository
from tests.conftest import auth_headers, build_pdf_with_text
from tests.processing.test_service import FakeMineruParser, _override_services

SECRET = "api-key-sentinel-do-not-persist"
SOURCE = "document-source-sentinel-do-not-persist"


def rejecting_adapter(status):
    def handle(request):
        return httpx.Response(
            status, json={"error": {"message": f"{SECRET}: {SOURCE}"}},
        )

    return OpenAICompatibleEmbeddingAdapter(
        base_url="https://embedding.test/v1", api_key=SECRET,
        profile=EmbeddingProfile(dimensions=3), max_retries=0,
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handle)),
    )


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_adapter_never_exposes_response_text_when_provider_echoes_secrets(
    status, caplog,
):
    with pytest.raises(AppError) as failure:
        rejecting_adapter(status).embed_query(SOURCE)
    exposed = str(failure.value) + repr(failure.value.details) + caplog.text
    assert SECRET not in exposed
    assert SOURCE not in exposed
    assert failure.value.details["status"] == status


def test_stage_error_and_logs_exclude_secrets_when_provider_echoes_request(
    client, api_prefix, register_user, session_factory, storage, caplog,
):
    caplog.set_level(logging.INFO)
    _override_services(
        client, session_factory=session_factory, storage=storage,
        mineru=FakeMineruParser(), resolver=MetadataResolver([]),
        embeddings=rejecting_adapter(401),
    )
    user = register_user(email="safe-errors@example.com")
    uploaded = client.post(
        f"{api_prefix}/papers", headers=auth_headers(user["access_token"]),
        files={"file": (
            "paper.pdf", build_pdf_with_text("attention"), "application/pdf",
        )},
    )
    assert uploaded.status_code == 202
    body = uploaded.json()
    stages = {stage["stage"]: stage for stage in body["ingestion_job"]["stages"]}
    assert stages["embedding"]["status"] == "failed"
    with session_factory() as session:
        job = IngestionRepository(session).get_job(UUID(body["ingestion_job"]["id"]))
        persisted = repr(job)
    for text in (uploaded.text, persisted, caplog.text):
        assert SECRET not in text
        assert SOURCE not in text


def test_request_preserves_client_budgets_when_embedding_overrides_read_timeout():
    budget = httpx.Timeout(connect=2, read=7, write=3, pool=4)
    seen = []

    def handle(request):
        seen.append(request.extensions["timeout"])
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1, 0, 0]}]},
        )

    client = httpx.Client(timeout=budget, transport=httpx.MockTransport(handle))
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="https://embedding.test/v1", profile=EmbeddingProfile(dimensions=3),
        http_client_factory=lambda: client,
    )
    adapter.embed_query("attention")
    assert client.timeout == budget
    assert seen == [{"connect": 2, "read": settings.embedding_timeout_seconds,
                     "write": 3, "pool": 4}]


def test_adapter_returns_safe_error_when_success_payload_has_sensitive_invalid_index():
    def handle(request):
        return httpx.Response(200, json={
            "data": [{"index": f"{SECRET}: {SOURCE}", "embedding": [1, 0, 0]}],
        })

    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="https://embedding.test/v1", profile=EmbeddingProfile(dimensions=3),
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(AppError) as failure:
        adapter.embed_query("attention")
    assert SECRET not in str(failure.value)
    assert SOURCE not in str(failure.value)


def test_adapter_rejects_sensitive_vector_values_when_provider_returns_strings():
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="https://embedding.test/v1", profile=EmbeddingProfile(dimensions=3),
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [
                {"index": 0, "embedding": [SECRET, SOURCE, SECRET]},
            ]}),
        )),
    )
    with pytest.raises(AppError) as failure:
        adapter.embed_query("attention")
    assert SECRET not in str(failure.value)
    assert SOURCE not in str(failure.value)
