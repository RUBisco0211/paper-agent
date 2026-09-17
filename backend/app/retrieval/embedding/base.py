"""Embedding adapter boundary.

向量提供方差异（模型维度、最大输入长度、是否需要 query/document 前缀、鉴权方式）
都收敛在适配器里：上层只认识 ``EmbeddingAdapter``，换模型/换服务是配置变更而非改代码。
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddingProfile:
    """一个已知模型的默认行为。

    只需要覆盖与默认不同的部分；未知模型走 ``DEFAULT_PROFILE``，
    由部署者通过环境变量补齐（维度必须与迁移里的向量列一致）。
    """

    dimensions: int = 1024
    max_input_chars: int = 6000
    #: 单个 HTTP 请求里允许的文本条数（供应商限制，例如 DashScope 为 10）
    max_batch_items: int = 32
    #: 单个请求的输入总字符上限（供应商常按 token 限制整批，如 DashScope）
    max_batch_chars: int = 24000
    query_prefix: str = ""
    document_prefix: str = ""
    notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


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


def prepare(text: str, *, prefix: str, max_input_chars: int) -> str:
    """统一处理前缀与长度上限：超出模型窗口时截断而不是提交失败。"""
    prepared = f"{prefix}{text}" if prefix else text
    return prepared[:max_input_chars]
