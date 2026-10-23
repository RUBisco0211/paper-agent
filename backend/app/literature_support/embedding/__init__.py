"""向量适配层：上层只依赖 ``EmbeddingAdapter``。"""

from app.literature_support.embedding.base import EmbeddingProfile, prepare
from app.literature_support.embedding.client import OpenAICompatibleEmbeddingAdapter
from app.literature_support.embedding.profiles import (
    DEFAULT_PROFILE,
    MODEL_PROFILES,
    profile_for,
)
from app.retrieval.ports import EmbeddingAdapter

__all__ = [
    "DEFAULT_PROFILE",
    "MODEL_PROFILES",
    "EmbeddingAdapter",
    "EmbeddingProfile",
    "OpenAICompatibleEmbeddingAdapter",
    "build_embedding_adapter",
    "prepare",
    "profile_for",
]


def build_embedding_adapter() -> EmbeddingAdapter:
    """按部署配置装配适配器。

    向量由平台统一产生：托管服务用部署方自己的 ``EMBEDDING_API_KEY``，
    自部署服务留空即不发送鉴权头。共享的 chunk 向量因此只属于平台，
    用户不参与付费。目前只有 ``openai_compatible`` 一种实现；
    新增提供方时在这里按 ``EMBEDDING_ADAPTER`` 分支注册，无需改动检索与流水线代码。
    """
    from app.platform.config import settings

    profile = profile_for(
        settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        max_input_chars=settings.embedding_max_input_chars,
        max_batch_items=settings.embedding_max_batch_items,
        max_batch_chars=settings.embedding_max_batch_chars,
        query_prefix=settings.embedding_query_prefix,
        document_prefix=settings.embedding_document_prefix,
    )
    return OpenAICompatibleEmbeddingAdapter(
        profile=profile,
        api_key=settings.embedding_api_key,
    )
