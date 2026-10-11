"""An image quote is resolved only through the authorized session scope."""

import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.retrieval.service import BoundPaperService


class BindingStub:
    def __init__(self, project_id=None):
        self.project_id = project_id

    def require(self, **_kwargs):
        return SimpleNamespace(project_id=self.project_id)


class LibraryStub:
    def get_entry(self, **_kwargs):
        return SimpleNamespace(user_paper=SimpleNamespace(title="图表文献"))

    def artifact_cache_version(self, **_kwargs):
        return "v1"

    def get_block(self, **_kwargs):
        return {"page": 2, "type": "chart", "has_image": True, "formula": None}

    def get_block_full_text(self, **_kwargs):
        return ""

    def get_block_image(self, **_kwargs):
        return b"small-image", "image/png"


def test_image_quote_resolves_bytes_after_scope_and_block_validation():
    paper_id = uuid4()
    library = LibraryStub()
    service = BoundPaperService(
        BindingStub(project_id=uuid4()), library,
        SimpleNamespace(paper_ids_of=lambda _project_id: {paper_id}),
    )
    result = service.resolve_quote(
        user_id=uuid4(), session_id=uuid4(), user_paper_id=paper_id,
        kind="parsed_block", version="v1", page=2, block_id=4,
        start=0, end=0, selected_text="", include_image=True,
    )
    assert base64.b64decode(result["image_base64"]) == b"small-image"
    assert result["image_media_type"] == "image/png"


def test_image_quote_rejects_a_paper_outside_the_project():
    service = BoundPaperService(
        BindingStub(project_id=uuid4()), LibraryStub(),
        SimpleNamespace(paper_ids_of=lambda _project_id: set()),
    )
    with pytest.raises(Exception, match="文献不在当前会话范围"):
        service.resolve_quote(
            user_id=uuid4(), session_id=uuid4(), user_paper_id=uuid4(),
            kind="parsed_block", version="v1", page=2, block_id=4,
            start=0, end=0, selected_text="", include_image=True,
        )
