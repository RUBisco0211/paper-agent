"""向量适配层：上层只依赖 ``EmbeddingAdapter``。"""

from .base import EmbeddingAdapter, EmbeddingProfile, prepare
from .openai_compatible import OpenAICompatibleEmbeddingAdapter
from .profiles import DEFAULT_PROFILE, MODEL_PROFILES, profile_for

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
    """按配置装配适配器。

    目前只有 ``openai_compatible`` 一种实现；新增提供方时在这里按
    ``EMBEDDING_ADAPTER`` 分支注册，无需改动检索与流水线代码。
    """
    from ...platform.config import settings

    profile = profile_for(
        settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        max_input_chars=settings.embedding_max_input_chars,
        max_batch_items=settings.embedding_max_batch_items,
        query_prefix=settings.embedding_query_prefix,
        document_prefix=settings.embedding_document_prefix,
    )
    return OpenAICompatibleEmbeddingAdapter(profile=profile)
