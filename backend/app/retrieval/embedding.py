"""Embedding provider client (OpenAI-compatible ``/embeddings``)."""

from collections.abc import Sequence

import httpx
import structlog

from ..platform.config import settings
from ..platform.errors import AppError, ErrorCode
from ..scholar.metadata import HttpClientFactory, default_http_client_factory

logger = structlog.get_logger(__name__)


class EmbeddingClient:
    """Instance-configured embedding model; never user supplied."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        http_client_factory: HttpClientFactory = default_http_client_factory,
    ) -> None:
        self._base_url = (
            base_url if base_url is not None else settings.embedding_api_url
        )
        self._api_key = api_key if api_key is not None else settings.embedding_api_key
        self._model = model or settings.embedding_model
        self._dimensions = dimensions or settings.embedding_dimensions
        self._client_factory = http_client_factory

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in one request; raises stable provider errors."""
        if not texts:
            return []
        if not self.is_configured:
            raise AppError(
                "Embedding 服务未配置",
                code=ErrorCode.PROVIDER_NOT_CONFIGURED,
                status_code=503,
            )

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {"model": self._model, "input": list(texts)}

        try:
            with self._client_factory() as client:
                response = client.post(
                    f"{self._base_url.rstrip('/')}/embeddings",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise AppError(
                "Embedding 服务响应超时",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "无法连接 Embedding 服务",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=502,
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            raise AppError(
                "Embedding 服务鉴权失败",
                code=ErrorCode.PROVIDER_NOT_CONFIGURED,
                status_code=503,
            )
        if response.status_code == 429:
            raise AppError(
                "Embedding 服务限流",
                code=ErrorCode.PROVIDER_RATE_LIMITED,
                status_code=429,
            )
        if response.status_code >= 400:
            raise AppError(
                "Embedding 服务返回错误",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=502,
            )

        data = response.json().get("data", [])
        vectors = [item.get("embedding") for item in sorted(data, key=_index_of)]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise AppError(
                "Embedding 服务返回的向量数量不匹配",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=502,
            )
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise AppError(
                    "Embedding 维度与实例配置不一致",
                    code=ErrorCode.PROVIDER_UNAVAILABLE,
                    status_code=502,
                )
        return vectors


def _index_of(item: dict) -> int:
    return int(item.get("index", 0))
