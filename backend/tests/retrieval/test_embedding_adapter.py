"""向量适配层：切换模型时的行为契约（离线，用 MockTransport）。"""

import json

import httpx
import pytest

from app.retrieval.embedding import OpenAICompatibleEmbeddingAdapter, profile_for
from app.retrieval.embedding.base import EmbeddingProfile


def _transport(dimensions: int = 3) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        payload = json.loads(request.content)
        texts = payload["input"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [0.1] * dimensions}
                    for index, _ in enumerate(texts)
                ],
            },
        )

    return httpx.MockTransport(handler), seen


def _adapter(
    transport: httpx.MockTransport,
    profile: EmbeddingProfile,
    *,
    api_key: str | None = None,
    base_url: str = "https://embedding.test/v1",
) -> OpenAICompatibleEmbeddingAdapter:
    return OpenAICompatibleEmbeddingAdapter(
        base_url=base_url,
        api_key=api_key,
        model="test-model",
        profile=profile,
        http_client_factory=lambda: httpx.Client(transport=transport),
    )


def test_documents_and_query_use_their_own_prefixes() -> None:
    transport, seen = _transport()
    profile = EmbeddingProfile(
        dimensions=3,
        max_input_chars=100,
        query_prefix="query: ",
        document_prefix="passage: ",
    )
    adapter = _adapter(transport, profile)

    adapter.embed_documents(["chunk text"])
    adapter.embed_query("what is attention?")

    assert json.loads(seen[0].content)["input"] == ["passage: chunk text"]
    assert json.loads(seen[1].content)["input"] == ["query: what is attention?"]


def test_long_input_is_truncated_to_the_model_window() -> None:
    transport, seen = _transport()
    adapter = _adapter(transport, EmbeddingProfile(dimensions=3, max_input_chars=10))

    adapter.embed_documents(["x" * 500])

    assert json.loads(seen[0].content)["input"] == ["x" * 10]


def test_unconfigured_adapter_reports_a_stable_code() -> None:
    transport, _ = _transport()
    adapter = _adapter(transport, EmbeddingProfile(dimensions=3), base_url="")

    with pytest.raises(Exception) as excinfo:
        adapter.embed_query("hello")

    assert getattr(excinfo.value, "code", None) == "provider_not_configured"


def test_dimension_mismatch_is_reported_instead_of_stored() -> None:
    transport, _ = _transport(dimensions=8)
    adapter = _adapter(transport, EmbeddingProfile(dimensions=3))

    with pytest.raises(Exception) as excinfo:
        adapter.embed_documents(["hello"])

    assert getattr(excinfo.value, "code", None) == "provider_unavailable"
    assert "维度与配置不一致" in str(excinfo.value)


def test_known_models_carry_their_defaults() -> None:
    bge = profile_for("BAAI/bge-m3")
    assert (bge.dimensions, bge.max_input_chars, bge.query_prefix) == (1024, 24000, "")

    nomic = profile_for("nomic-ai/nomic-embed-text-v1.5")
    assert nomic.dimensions == 768
    assert nomic.document_prefix.startswith("search_document")

    e5 = profile_for("intfloat/e5-large-v2")
    assert (e5.query_prefix, e5.document_prefix) == ("query: ", "passage: ")

    # 未知模型走默认档案，由部署者用环境变量补齐
    unknown = profile_for("some/private-model", dimensions=512, max_input_chars=1000)
    assert (unknown.dimensions, unknown.max_input_chars) == (512, 1000)


def test_explicit_settings_override_profile_prefixes() -> None:
    profile = profile_for("BAAI/bge-m3", query_prefix="Q: ", document_prefix="D: ")

    assert (profile.query_prefix, profile.document_prefix) == ("Q: ", "D: ")
    # 维度仍来自模型档案
    assert profile.dimensions == 1024


def test_provider_batch_limit_splits_requests(monkeypatch) -> None:
    """供应商限制单请求条数时（例如 DashScope 10 条），适配器负责切分。"""
    transport, seen = _transport()
    # _transport 按输入条数返回等量向量，这里用 dims=3 与档案一致
    adapter = _adapter(transport, EmbeddingProfile(dimensions=3, max_batch_items=2))

    vectors = adapter.embed_documents(["a", "b", "c", "d", "e"])

    assert len(vectors) == 5
    assert [len(json.loads(request.content)["input"]) for request in seen] == [2, 2, 1]


def test_dashscope_profile_keeps_its_small_batch_limit() -> None:
    assert profile_for("text-embedding-v3").max_batch_items == 10
    assert profile_for("BAAI/bge-m3").max_batch_items == 32


def test_request_batches_respect_the_char_budget(tmp_path) -> None:
    """除了条数，供应商还限制整批 token/字符时也要拆包。"""
    from app.retrieval.embedding.openai_compatible import _split_batches

    batches = _split_batches(["a" * 8, "b" * 8, "c" * 8], max_items=10, max_chars=20)

    assert [len(batch) for batch in batches] == [2, 1]
    assert all(sum(len(text) for text in batch) <= 20 for batch in batches)
    # 单个超限文本单独成包，不会被丢弃
    assert _split_batches(["x" * 50], max_items=10, max_chars=10) == [["x" * 50]]


def test_dashscope_profile_bounds_both_items_and_chars() -> None:
    dashscope = profile_for("text-embedding-v3")

    assert dashscope.max_batch_items == 10
    assert dashscope.max_batch_chars <= 24000
    assert dashscope.dimensions == 1024
