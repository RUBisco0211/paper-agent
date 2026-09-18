"""Agent 的三个只读论文工具。

范围（全局 / 项目 / 单篇文献）由后端在构建工具时注入，**不来自模型参数**：
模型无法通过传 user_id 或扩大 scope 越权。检索证据会登记为 Citation，
模型只能引用登记过的 citation_id，展开时再按会话与用户校验一次。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

import structlog

from ..library.application import PaperLibraryService
from ..library.persistence import PaperRepository
from ..platform.config import settings
from ..platform.database import SessionFactory
from ..projects.persistence import ProjectRepository
from ..retrieval.application import SearchService
from ..retrieval.domain import SearchScope
from ..retrieval.embedding import build_embedding_adapter
from ..retrieval.persistence import ChunkRepository
from .application import CitationService
from .persistence import SessionRepository

logger = structlog.get_logger(__name__)

DEFAULT_PAPER_LIMIT = 20
MAX_PAPER_LIMIT = 50
DEFAULT_EVIDENCE_LIMIT = 8
MAX_EVIDENCE_LIMIT = 20
SNIPPET_CHARS = 600


@dataclass(frozen=True, slots=True)
class SessionToolContext:
    """一次会话回合里工具的授权上下文。"""

    session_id: UUID
    user_id: UUID
    project_id: UUID | None = None
    paper_id: UUID | None = None

    @property
    def scope_label(self) -> str:
        if self.project_id is not None:
            return "project"
        if self.paper_id is not None:
            return "paper"
        return "library"


@dataclass(slots=True)
class ToolServices:
    """工具每次调用自建 Session 与仓储，避免跨线程共享 Session。

    三个 factory 可注入，便于在测试里替换成假实现（工具逻辑本身不依赖数据库）。
    """

    session_factory: SessionFactory
    library_factory: Callable[[object], PaperLibraryService] | None = None
    search_factory: Callable[[object], SearchService] | None = None
    citation_factory: Callable[[object], CitationService] | None = None
    collected_citations: list[str] = field(default_factory=list)

    def library(self, session) -> PaperLibraryService:
        if self.library_factory is not None:
            return self.library_factory(session)
        from ..ingestion.dependencies import build_ingestion_service
        from ..platform.storage import get_object_storage
        from ..scholar.metadata import build_default_resolver
        from ..scholar.pdf_fetch import PdfFetcher

        storage = get_object_storage()
        return PaperLibraryService(
            PaperRepository(session),
            build_ingestion_service(
                session=session,
                storage=storage,
                session_factory=self.session_factory,
                scheduler=_NoopScheduler(),
            ),
            storage,
            build_default_resolver(),
            PdfFetcher(max_bytes=settings.max_pdf_bytes),
        )

    def search(self, session) -> SearchService:
        if self.search_factory is not None:
            return self.search_factory(session)
        return SearchService(
            ChunkRepository(session),
            PaperRepository(session),
            ProjectRepository(session),
            build_embedding_adapter(),
            keyword_top_n=settings.keyword_top_n,
            vector_top_n=settings.vector_top_n,
            rrf_k=settings.rrf_k,
            max_evidence=settings.max_evidence_chunks,
            max_evidence_per_paper=settings.max_evidence_per_paper,
        )

    def citations(self, session) -> CitationService:
        if self.citation_factory is not None:
            return self.citation_factory(session)
        return CitationService(SessionRepository(session))


class _NoopScheduler:
    """工具只读，不会提交后台任务；这里只为满足构造签名。"""

    def submit(self, factory, *, name: str) -> None:  # pragma: no cover - 不会调用
        raise RuntimeError("只读工具不应提交后台任务")


class SessionTools:
    """绑定到一个会话范围的三只只读工具。"""

    def __init__(self, context: SessionToolContext, services: ToolServices) -> None:
        self._context = context
        self._services = services

    @property
    def collected_citations(self) -> list[str]:
        """本次回合登记过的 citation_id（供执行器写入 Assistant Entry）。"""
        return list(self._services.collected_citations)

    # list_papers ----------------------------------------------------------
    def list_papers(self, limit: int = DEFAULT_PAPER_LIMIT, offset: int = 0) -> dict:
        """列出本次会话授权范围内的文献。

        返回每篇文献的稳定条目 ID、标题与是否已有可检索全文，供后续检索或引用。

        Args:
            limit: 返回条数上限（1-50）。
            offset: 分页偏移。
        """
        limit = _clamp(limit, 1, MAX_PAPER_LIMIT)
        offset = max(0, offset)
        with self._services.session_factory() as session:
            library = self._services.library(session)
            if self._context.paper_id is not None:
                entries = library.entries_for(
                    user_id=self._context.user_id,
                    user_paper_ids=[self._context.paper_id],
                )
                total = len(entries)
                page = entries[offset : offset + limit]
            elif self._context.project_id is not None:
                member_ids = list(
                    ProjectRepository(session).paper_ids_of(self._context.project_id),
                )
                entries = library.entries_for(
                    user_id=self._context.user_id,
                    user_paper_ids=member_ids,
                )
                total = len(entries)
                page = entries[offset : offset + limit]
            else:
                page, total = library.list_entries(
                    user_id=self._context.user_id,
                    limit=limit,
                    offset=offset,
                )

        papers = [
            {
                "paper_id": str(entry.user_paper.id),
                "title": entry.user_paper.title,
                "authors": entry.user_paper.authors[:5],
                "year": entry.user_paper.year,
                "venue": entry.user_paper.venue,
                "has_fulltext": entry.capabilities.has_fulltext,
            }
            for entry in page
        ]
        logger.info(
            "agent.tool.list_papers",
            session_id=str(self._context.session_id),
            scope=self._context.scope_label,
            returned=len(papers),
            total=total,
        )
        return {
            "scope": self._context.scope_label,
            "total": total,
            "returned": len(papers),
            "papers": papers,
            "note": "只有 has_fulltext=true 的文献能作为全文证据被引用。",
        }

    # search_papers --------------------------------------------------------
    def search_papers(self, query: str, limit: int = DEFAULT_EVIDENCE_LIMIT) -> dict:
        """在授权范围内检索论文原文证据，返回可引用的片段与 Citation ID。

        回答中引用原文时必须使用这里返回的 citation_id；证据不足时要如实说明，
        不能用通用知识替代。

        Args:
            query: 检索问题或关键词（英文优先）。
            limit: 证据条数上限（1-20）。
        """
        limit = _clamp(limit, 1, MAX_EVIDENCE_LIMIT)
        scope, paper_ids = self._search_scope()
        with self._services.session_factory() as session:
            outcome = self._services.search(session).search(
                user_id=self._context.user_id,
                query=query,
                scope=scope,
                limit=limit,
                project_id=self._context.project_id,
                paper_ids=paper_ids,
            )
            citations = self._services.citations(session).record_evidence(
                session_id=self._context.session_id,
                evidence=outcome.evidence,
            )

        self._services.collected_citations.extend(
            citation.citation_id for citation in citations
        )
        evidence = [
            {
                "citation_id": citation.citation_id,
                "paper_id": str(citation.user_paper_id),
                "page_start": citation.page_start,
                "page_end": citation.page_end,
                "title_path": citation.title_path,
                "snippet": citation.snippet[:SNIPPET_CHARS],
            }
            for citation in citations
        ]
        logger.info(
            "agent.tool.search_papers",
            session_id=str(self._context.session_id),
            scope=self._context.scope_label,
            status=outcome.status.value,
            evidence=len(evidence),
        )
        return {
            "scope": self._context.scope_label,
            "retrieval_status": outcome.status.value,
            "channels": {
                name: report.status.value for name, report in outcome.channels.items()
            },
            "evidence": evidence,
            "note": (
                "没有 evidence 表示授权范围内没有相关证据；"
                "retrieval_status=degraded 表示只有部分检索通道可用，"
                "unavailable 表示检索服务故障，两者都不能解释为论文没有相关内容。"
            ),
        }

    # get_paper_excerpt ----------------------------------------------------
    def get_paper_excerpt(self, citation_id: str) -> dict:
        """展开某个 Citation 对应的原文片段（含页码），用于核对结论。

        Args:
            citation_id: search_papers 返回的 citation_id。
        """
        with self._services.session_factory() as session:
            citation = self._services.citations(session).get(
                user_id=self._context.user_id,
                session_id=self._context.session_id,
                citation_id=citation_id,
            )
            entry = self._services.library(session).get_entry(
                user_id=self._context.user_id,
                user_paper_id=citation.user_paper_id,
            )

        logger.info(
            "agent.tool.get_paper_excerpt",
            session_id=str(self._context.session_id),
            citation_id=citation_id,
        )
        return {
            "citation_id": citation.citation_id,
            "paper_id": str(citation.user_paper_id),
            "paper_title": entry.user_paper.title if entry else None,
            "title_path": citation.title_path,
            "page_start": citation.page_start,
            "page_end": citation.page_end,
            "chunk_ids": [str(chunk_id) for chunk_id in citation.chunk_ids],
            "text": citation.snippet,
        }

    # Internals ------------------------------------------------------------
    def _search_scope(self) -> tuple[SearchScope, list[UUID] | None]:
        if self._context.paper_id is not None:
            return SearchScope.PAPER, [self._context.paper_id]
        if self._context.project_id is not None:
            return SearchScope.PROJECT, None
        return SearchScope.LIBRARY, None


def _clamp(value: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))
