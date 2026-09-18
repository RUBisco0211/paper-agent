"""三个只读工具的行为契约（离线：不连数据库、不调模型）。"""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.library.application import LibraryEntry
from app.library.domain import (
    MetadataStatus,
    Paper,
    PaperSource,
    UserPaper,
)
from app.retrieval.domain import (
    ChannelReport,
    ChannelStatus,
    Evidence,
    SearchOutcome,
    SearchScope,
    SearchStatus,
)
from app.sessions.domain import Citation
from app.sessions.tools import SessionToolContext, SessionTools, ToolServices

USER_ID = uuid4()
SESSION_ID = uuid4()


class _Session:
    """占位 Session：工具只把它透传给仓储，测试里不需要真实数据库。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _entry(paper_id: UUID, title: str, *, has_fulltext: bool = True) -> LibraryEntry:
    user_paper = UserPaper(
        id=paper_id,
        user_id=USER_ID,
        paper_id=uuid4(),
        title=title,
        authors=["A. Author"],
        year=2024,
        source=PaperSource.UPLOAD,
        metadata_status=MetadataStatus.RECOGNIZED,
    )
    paper = Paper(
        id=user_paper.paper_id,
        file_hash="a" * 64,
        byte_size=1,
        page_count=10,
        bibliographic=None,
        metadata_status=MetadataStatus.RECOGNIZED,
        metadata_sources=None,
        has_metadata=True,
        has_fulltext=has_fulltext,
        has_keyword_index=has_fulltext,
        has_embedding=False,
        mineru_version=None,
        created_at=user_paper.created_at or __import__("datetime").datetime.now(),
        updated_at=user_paper.updated_at or __import__("datetime").datetime.now(),
    )
    return LibraryEntry(
        user_paper=user_paper,
        paper=paper,
        capabilities=user_paper.capabilities(paper),
        latest_job=None,
    )


@dataclass
class FakeLibrary:
    entries: list[LibraryEntry]
    recorded: list[dict] | None = None

    def list_entries(self, *, user_id, limit, offset, query=None):
        return self.entries[offset : offset + limit], len(self.entries)

    def entries_for(self, *, user_id, user_paper_ids):
        wanted = set(user_paper_ids)
        return [entry for entry in self.entries if entry.user_paper.id in wanted]

    def get_entry(self, *, user_id, user_paper_id):
        return next(
            (e for e in self.entries if e.user_paper.id == user_paper_id),
            None,
        )


@dataclass
class FakeSearch:
    evidence: list[tuple[UUID, str]]
    calls: list[dict]

    def search(self, *, user_id, query, scope, limit, project_id=None, paper_ids=None):
        self.calls.append(
            {
                "query": query,
                "scope": scope,
                "project_id": project_id,
                "paper_ids": paper_ids,
            },
        )
        evidence = [
            Evidence(
                paper_id=paper_id,
                chunk_ids=[uuid4()],
                title_path="1 Introduction",
                snippet=snippet,
                page_start=3,
                page_end=4,
                score=0.5,
                chunk_index=0,
            )
            for paper_id, snippet in self.evidence[:limit]
        ]
        return SearchOutcome(
            status=SearchStatus.DEGRADED,
            evidence=evidence,
            channels={
                "keyword": ChannelReport("keyword", ChannelStatus.OK, len(evidence)),
                "vector": ChannelReport("vector", ChannelStatus.SKIPPED, 0),
            },
        )


@dataclass
class FakeCitations:
    recorded: list
    registry: dict

    def record_evidence(self, *, session_id, evidence):
        citations = []
        for item in evidence:
            citation = Citation(
                citation_id=f"cit_{len(self.registry):04d}",
                session_id=session_id,
                user_paper_id=item.paper_id,
                chunk_ids=list(item.chunk_ids),
                title_path=item.title_path,
                snippet=item.snippet,
                page_start=item.page_start,
                page_end=item.page_end,
            )
            self.registry[citation.citation_id] = citation
            citations.append(citation)
        self.recorded.extend(citations)
        return citations

    def get(self, *, user_id, session_id, citation_id):
        return self.registry[citation_id]


@pytest.fixture
def tools_factory():
    """返回 (工具, 假实现)：假实现是共享实例，便于断言调用与登记结果。"""

    def _build(context: SessionToolContext, *, entries=None, evidence=None):
        library = FakeLibrary(entries or [])
        search = FakeSearch(evidence or [], [])
        citations = FakeCitations([], {})
        services = ToolServices(
            session_factory=lambda: _Session(),
            library_factory=lambda session: library,
            search_factory=lambda session: search,
            citation_factory=lambda session: citations,
        )
        return SessionTools(context, services), (library, search, citations)

    return _build


def test_list_papers_reports_scope_and_fulltext_capability(tools_factory) -> None:
    paper_id = uuid4()
    context = SessionToolContext(session_id=SESSION_ID, user_id=USER_ID)
    tools, _ = tools_factory(
        context,
        entries=[_entry(paper_id, "Attention Is All You Need")],
    )

    result = tools.list_papers(limit=10)

    assert result["scope"] == "library"
    assert result["total"] == 1
    assert result["papers"][0] == {
        "paper_id": str(paper_id),
        "title": "Attention Is All You Need",
        "authors": ["A. Author"],
        "year": 2024,
        "venue": None,
        "has_fulltext": True,
    }


def test_list_papers_is_limited_to_the_session_scope(tools_factory) -> None:
    inside, outside = uuid4(), uuid4()
    context = SessionToolContext(
        session_id=SESSION_ID,
        user_id=USER_ID,
        paper_id=inside,
    )
    tools, _ = tools_factory(
        context,
        entries=[_entry(inside, "Inside"), _entry(outside, "Outside")],
    )

    result = tools.list_papers()

    assert [paper["title"] for paper in result["papers"]] == ["Inside"]
    assert result["scope"] == "paper"


def test_search_papers_registers_citations_and_passes_scope(tools_factory) -> None:
    paper_id = uuid4()
    context = SessionToolContext(
        session_id=SESSION_ID,
        user_id=USER_ID,
        project_id=uuid4(),
    )
    tools, fakes = tools_factory(
        context, evidence=[(paper_id, "attention is all you need")]
    )

    result = tools.search_papers("attention", limit=5)

    assert result["scope"] == "project"
    assert result["retrieval_status"] == "degraded"
    assert result["channels"]["vector"] == "skipped"
    evidence = result["evidence"][0]
    assert evidence["citation_id"].startswith("cit_")
    assert evidence["paper_id"] == str(paper_id)
    assert evidence["page_start"] == 3
    # 引用登记在工具层完成，模型只能引用登记过的 id
    assert tools._services.collected_citations == [evidence["citation_id"]]
    # 范围来自会话上下文，不是工具参数
    call = fakes[1].calls[0]
    assert call["scope"] is SearchScope.PROJECT
    assert call["project_id"] == context.project_id


def test_search_papers_marks_empty_evidence_as_no_evidence(tools_factory) -> None:
    context = SessionToolContext(session_id=SESSION_ID, user_id=USER_ID)
    tools, _ = tools_factory(context, evidence=[])

    result = tools.search_papers("nonexistent topic")

    assert result["evidence"] == []
    assert "没有 evidence" in result["note"]


def test_get_paper_excerpt_returns_stored_evidence(tools_factory) -> None:
    paper_id = uuid4()
    context = SessionToolContext(session_id=SESSION_ID, user_id=USER_ID)
    tools, _ = tools_factory(
        context,
        entries=[_entry(paper_id, "Attention Is All You Need")],
        evidence=[(paper_id, "scaled dot product attention")],
    )
    citation_id = tools.search_papers("attention")["evidence"][0]["citation_id"]

    excerpt = tools.get_paper_excerpt(citation_id)

    assert excerpt["citation_id"] == citation_id
    assert excerpt["paper_id"] == str(paper_id)
    assert excerpt["paper_title"] == "Attention Is All You Need"
    assert excerpt["title_path"] == "1 Introduction"
    assert excerpt["page_start"] == 3
    assert "scaled dot product attention" in excerpt["text"]
    assert excerpt["chunk_ids"]


def test_tool_limits_are_clamped(tools_factory) -> None:
    context = SessionToolContext(session_id=SESSION_ID, user_id=USER_ID)
    tools, _ = tools_factory(context, entries=[_entry(uuid4(), "X")])

    # 越界与非法输入都不会抛错，只会被收紧
    assert tools.list_papers(limit=9999)["total"] == 1
    assert tools.list_papers(limit="bad")["papers"]
