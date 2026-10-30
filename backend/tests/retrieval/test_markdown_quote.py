"""A markdown quote is accepted only when the passage exists in that version."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.retrieval.service import BoundPaperService

FULL_TEXT = "# 标题\n\n我们提出的方法在三个仿真环境上验证了安全性。"


class BindingStub:
    """A global session: every paper the user owns is readable."""

    def require(self, **_kwargs):
        return SimpleNamespace(project_id=None)


class LibraryStub:
    def __init__(self, markdown: str = FULL_TEXT, version: str = "v1") -> None:
        self._markdown = markdown
        self._version = version

    def get_entry(self, **_kwargs):
        return SimpleNamespace(
            user_paper=SimpleNamespace(),
            paper=SimpleNamespace(title="全文文献", page_count=8),
        )

    def artifact_cache_version(self, **_kwargs):
        return self._version

    def read_markdown(self, **_kwargs):
        return self._markdown


def resolve(service: BoundPaperService, **overrides):
    arguments = {
        "user_id": uuid4(),
        "session_id": uuid4(),
        "user_paper_id": uuid4(),
        "kind": "markdown_selection",
        "version": "v1",
        "page": None,
        "block_id": None,
        "start": None,
        "end": None,
        "selected_text": FULL_TEXT.split("\n\n")[1],
    }
    arguments.update(overrides)
    return service.resolve_quote(**arguments)


def service_for(library: LibraryStub) -> BoundPaperService:
    return BoundPaperService(
        BindingStub(), library, SimpleNamespace(paper_ids_of=lambda _id: set())
    )


def test_markdown_quote_resolves_with_the_paper_title_and_no_page():
    result = resolve(service_for(LibraryStub()))

    assert result["title"] == "全文文献"
    assert result["page"] is None


def test_markdown_quote_matches_after_collapsing_reader_whitespace():
    result = resolve(
        service_for(LibraryStub()),
        selected_text="我们提出的方法\n\n在三个仿真环境上验证了安全性。",
    )

    assert result["title"] == "全文文献"


def test_markdown_quote_rejects_a_passage_missing_from_the_full_text():
    with pytest.raises(ValueError, match="selection_mismatch"):
        resolve(service_for(LibraryStub()), selected_text="文档里没有这句话")


def test_markdown_quote_rejects_a_stale_artifact_version():
    with pytest.raises(ValueError, match="artifact_version_changed"):
        resolve(service_for(LibraryStub(version="v2")))


def test_markdown_quote_rejects_a_request_for_image_bytes():
    with pytest.raises(ValueError, match="image_unavailable"):
        resolve(service_for(LibraryStub()), include_image=True)
