"""OpenAI-compatible ``/embeddings`` adapter.

覆盖 OpenAI、text-embeddings-inference、Ollama、vLLM 等所有提供该路由的服务。
模型差异（维度、截断长度、query/document 前缀）由 :mod:`profiles` 描述，
适配器只负责组装请求、解析响应并把失败映射成稳定错误码。
"""

from collections.abc import Sequence

import httpx
import structlog

from ...platform.config import settings
from ...platform.errors import AppError, ErrorCode
from ...scholar.metadata import HttpClientFactory, default_http_client_factory
from .base import EmbeddingProfile, prepare

logger = structlog.get_logger(__name__)


class OpenAICompatibleEmbeddingAdapter:
    """实例级配置的向量服务；模型与维度永不由用户提供。"""

    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        profile: EmbeddingProfile | None = None,
        http_client_factory: HttpClientFactory = default_http_client_factory,
    ) -> None:
        self._base_url = (
            base_url if base_url is not None else settings.embedding_api_url
        )
        self._api_key = api_key if api_key is not None else settings.embedding_api_key
        self._model = model or settings.embedding_model
        self._profile = profile or EmbeddingProfile(
            dimensions=settings.embedding_dimensions,
        )
        self._client_factory = http_client_factory

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._profile.dimensions

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url)

    # EmbeddingAdapter -----------------------------------------------------
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Chunk 向量：套文档前缀，并按模型窗口截断而不是提交失败。"""
        return self._embed(
            [
                prepare(
                    text,
                    prefix=self._profile.document_prefix,
                    max_input_chars=self._profile.max_input_chars,
                )
                for text in texts
            ],
        )

    def embed_query(self, text: str) -> list[float]:
        """查询向量：套查询前缀（检索模型常要求 query/document 不同前缀）。"""
        return self._embed(
            [
                prepare(
                    text,
                    prefix=self._profile.query_prefix,
                    max_input_chars=self._profile.max_input_chars,
                ),
            ],
        )[0]

    # Provider call --------------------------------------------------------
    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
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

        if response.status_code in {401, 403}:
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
                f"Embedding 服务返回错误（HTTP {response.status_code}）",
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
            if len(vector) != self._profile.dimensions:
                raise AppError(
                    f"Embedding 维度与配置不一致（期望 {self._profile.dimensions}，"
                    f"实际 {len(vector)}）",
                    code=ErrorCode.PROVIDER_UNAVAILABLE,
                    status_code=502,
                )
        return vectors


def _index_of(item: dict) -> int:
    return int(item.get("index", 0))
