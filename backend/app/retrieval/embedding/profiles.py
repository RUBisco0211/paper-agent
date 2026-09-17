"""Known embedding models and their defaults.

维度必须与 Alembic 迁移里的 ``chunks.embedding`` 一致；不一致时启动会记录明确错误，
需要先做一次离线迁移（见 backend/README 的 Embedding 章节）。
"""

from .base import EmbeddingProfile

DEFAULT_PROFILE = EmbeddingProfile(
    notes="未知模型：使用环境变量提供的维度与截断长度",
)

# 默认选型：多语言、8192 上下文、无需前缀，适合英文论文长句
MODEL_PROFILES: dict[str, EmbeddingProfile] = {
    # 同一份档案同时适用于自建 TEI 与云上同款模型（如 SiliconFlow 的 BAAI/bge-m3）
    "baai/bge-m3": EmbeddingProfile(
        dimensions=1024,
        max_input_chars=24000,
        max_batch_items=32,
        max_batch_chars=32000,
        notes="多语言，8192 上下文，无需前缀；自建 TEI 与 SiliconFlow 均为此维度",
    ),
    "baai/bge-large-en-v1.5": EmbeddingProfile(
        dimensions=1024,
        max_input_chars=1800,
        notes="英文，512 上下文：chunk 需要更短",
    ),
    "baai/bge-base-en-v1.5": EmbeddingProfile(dimensions=768, max_input_chars=1800),
    "baai/bge-small-en-v1.5": EmbeddingProfile(dimensions=384, max_input_chars=1800),
    "intfloat/e5-large-v2": EmbeddingProfile(
        dimensions=1024,
        max_input_chars=1800,
        query_prefix="query: ",
        document_prefix="passage: ",
        notes="需要 query/passage 前缀",
    ),
    "nomic-ai/nomic-embed-text-v1.5": EmbeddingProfile(
        dimensions=768,
        max_input_chars=8000,
        query_prefix="search_query: ",
        document_prefix="search_document: ",
        notes="需要 search_query/search_document 前缀",
    ),
    "google/embeddinggemma-300m": EmbeddingProfile(
        dimensions=768,
        max_input_chars=8000,
        query_prefix="task: search result | query: ",
        document_prefix="title: none | text: ",
        notes="需要 task 前缀，否则召回明显下降",
    ),
    "qwen/qwen3-embedding-0.6b": EmbeddingProfile(
        dimensions=1024,
        max_input_chars=24000,
        query_prefix=(
            "Instruct: Given a web search query, retrieve relevant passages\nQuery: "
        ),
        notes="32K 上下文，支持 Matryoshka 截断",
    ),
    "text-embedding-3-small": EmbeddingProfile(
        dimensions=1536,
        max_input_chars=8000,
        max_batch_items=2048,
    ),
    "text-embedding-3-large": EmbeddingProfile(
        dimensions=3072,
        max_input_chars=8000,
        max_batch_items=2048,
    ),
    # 阿里云百炼（OpenAI 兼容模式）：1024 维；单请求最多 10 条且整批 token 有上限，
    # 因此同时收紧条数与总字符预算（约 8192 tokens ≈ 2 万英文字符的保守取值）
    "text-embedding-v3": EmbeddingProfile(
        dimensions=1024,
        max_input_chars=6000,
        max_batch_items=10,
        max_batch_chars=12000,
        notes="DashScope，单请求 ≤10 条且整批 token 有上限",
    ),
    "text-embedding-v4": EmbeddingProfile(
        dimensions=1024,
        max_input_chars=6000,
        max_batch_items=10,
        max_batch_chars=12000,
        notes="DashScope Qwen3-Embedding 系列，单请求 ≤10 条且整批 token 有上限",
    ),
    # 智谱：维度可调（默认 2048），这里用 1024 以匹配现有向量列
    "embedding-3": EmbeddingProfile(
        dimensions=1024,
        max_input_chars=4000,
        max_batch_items=64,
        notes="智谱 embedding-3，需在请求维度上取 1024",
    ),
}


def profile_for(
    model: str,
    *,
    dimensions: int | None = None,
    max_input_chars: int | None = None,
    max_batch_items: int | None = None,
    max_batch_chars: int | None = None,
    query_prefix: str | None = None,
    document_prefix: str | None = None,
) -> EmbeddingProfile:
    """按模型名取默认行为，显式配置优先。"""
    base = MODEL_PROFILES.get(model.strip().lower(), DEFAULT_PROFILE)
    return EmbeddingProfile(
        dimensions=dimensions or base.dimensions,
        max_input_chars=max_input_chars or base.max_input_chars,
        max_batch_items=max_batch_items or base.max_batch_items,
        max_batch_chars=max_batch_chars or base.max_batch_chars,
        query_prefix=base.query_prefix if query_prefix is None else query_prefix,
        document_prefix=(
            base.document_prefix if document_prefix is None else document_prefix
        ),
        notes=base.notes,
    )
