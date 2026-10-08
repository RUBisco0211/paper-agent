"""Vector generation required by search and indexing."""

from collections.abc import Sequence
from typing import Protocol


class EmbeddingAdapter(Protocol):
    """检索层唯一依赖的接口。"""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    @property
    def is_configured(self) -> bool: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """把 chunk 文本转成向量（含文档前缀与截断）。"""
        ...

    def embed_query(self, text: str) -> list[float]:
        """把查询文本转成向量（含查询前缀与截断）。"""
        ...


class PaperDiscoveryAdapter(Protocol):
    def search(self, query: str, limit: int) -> "PaperDiscoveryResult": ...


class PaperDiscoveryResult(Protocol):
    papers: list[dict]
    failed_sources: list[str]
