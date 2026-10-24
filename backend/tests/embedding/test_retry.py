"""向量化调用对可恢复失败的退避重试（离线，用 MockTransport）。"""

import json

import httpx
import pytest

from app.literature_support.embedding import OpenAICompatibleEmbeddingAdapter
from app.literature_support.embedding.base import EmbeddingProfile
from app.platform.errors import AppError, ErrorCode

PROFILE = EmbeddingProfile(dimensions=3, max_input_chars=100)


def _ok_response(texts: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [
                {"index": index, "embedding": [0.1] * 3}
                for index, _ in enumerate(texts)
            ],
        },
    )


def _adapter(
    handler,
    *,
    max_retries: int = 3,
    backoffs: list[float] | None = None,
) -> OpenAICompatibleEmbeddingAdapter:
    """Adapter wired to a scripted handler; sleeps are recorded, not taken."""
    recorded = backoffs if backoffs is not None else []
    return OpenAICompatibleEmbeddingAdapter(
        base_url="https://embedding.test/v1",
        api_key=None,
        model="test-model",
        profile=PROFILE,
        http_client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(handler),
        ),
        max_retries=max_retries,
        retry_backoff=0.5,
        sleeper=recorded.append,
    )


def test_a_rate_limited_request_is_retried_until_the_provider_answers() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return _ok_response(json.loads(request.content)["input"])

    backoffs: list[float] = []
    adapter = _adapter(handler, backoffs=backoffs)

    vectors = adapter.embed_query("what is attention?")

    assert len(calls) == 3
    assert len(vectors) == 3
    # Exponential: the wait doubles between attempts.
    assert backoffs == [0.5, 1.0]


def test_a_rate_limited_request_reports_the_stable_code_after_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    adapter = _adapter(handler, max_retries=2)

    try:
        adapter.embed_query("what is attention?")
    except AppError as exc:
        assert exc.code is ErrorCode.PROVIDER_RATE_LIMITED
    else:
        raise AssertionError("a spent retry budget must surface as rate limited")

    assert len(calls) == 3


def test_an_invalid_key_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    adapter = _adapter(handler)

    try:
        adapter.embed_query("what is attention?")
    except AppError as exc:
        assert exc.code is ErrorCode.PROVIDER_NOT_CONFIGURED
    else:
        raise AssertionError("a rejected key is not a transient failure")

    assert len(calls) == 1


def test_a_refused_connection_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("connection refused")

    adapter = _adapter(handler)

    try:
        adapter.embed_query("what is attention?")
    except AppError as exc:
        assert exc.code is ErrorCode.PROVIDER_UNAVAILABLE
    else:
        raise AssertionError("the service being down is not a transient blip")

    assert len(calls) == 1


@pytest.mark.parametrize("failure_kind", ["429", "503", "timeout"])
@pytest.mark.parametrize("budget", [0, 2])
def test_adapter_stops_without_extra_wait_when_retry_budget_is_exhausted(
    failure_kind, budget,
):
    calls = []
    waits = []

    def handler(request):
        calls.append(request)
        if failure_kind == "timeout":
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(int(failure_kind))

    with pytest.raises(AppError):
        _adapter(handler, max_retries=budget, backoffs=waits).embed_query("attention")
    assert len(calls) == budget + 1
    assert waits == [0.5 * 2 ** attempt for attempt in range(budget)]


@pytest.mark.parametrize("failure_kind", ["429", "503", "timeout"])
def test_adapter_returns_vector_when_last_allowed_attempt_succeeds(failure_kind):
    calls = []
    waits = []

    def handler(request):
        calls.append(request)
        if len(calls) == 3:
            return _ok_response(["attention"])
        if failure_kind == "timeout":
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(int(failure_kind))

    result = _adapter(handler, max_retries=2, backoffs=waits).embed_query("attention")
    assert result == [0.1] * 3
    assert len(calls) == 3
    assert waits == [0.5, 1.0]
