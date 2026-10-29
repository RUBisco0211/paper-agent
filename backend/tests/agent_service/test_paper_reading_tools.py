"""The agent reads pages and figures only through the bound business API."""

import asyncio
import base64
from types import SimpleNamespace
from uuid import uuid4

from agentscope.message import DataBlock, TextBlock
from agentscope.tool import Toolkit

from agent_service.paper_agent import PaperAgent
from agent_service.tools import build_agent_tools
from agent_service.tools.base import PaperImageTool
from agent_service.tools.library import build_library_tools

PNG = b"\x89PNG\r\n\x1a\nfigure"


def _calls(monkeypatch):
    recorded = []

    async def request(method, path, **kwargs):
        recorded.append((method, path, kwargs))
        if path == "paper-page":
            return {
                "title": "Attention",
                "page": 2,
                "total_pages": 4,
                "markdown": "Second page body",
                "images": [{"block_id": 7, "caption": "Figure 1"}],
                "truncated": False,
                "omitted_block_ids": [],
            }
        return {
            "title": "Attention",
            "page": 2,
            "caption": "Figure 1",
            "image_base64": base64.b64encode(PNG).decode("ascii"),
            "image_media_type": "image/png",
        }

    monkeypatch.setattr("agent_service.tools.library.business_request", request)
    return recorded


def _tool(name):
    return next(
        tool
        for tool in build_library_tools(str(uuid4()), str(uuid4()))
        if tool.name == name
    )


def test_library_tools_expose_page_and_figure_readers_when_built() -> None:
    names = {tool.name for tool in build_library_tools(str(uuid4()), str(uuid4()))}

    assert names == {"list_papers", "search_papers", "read_paper", "read_paper_image"}


def test_page_reader_asks_for_one_page_of_the_named_paper(monkeypatch) -> None:
    recorded = _calls(monkeypatch)
    paper_id = str(uuid4())

    asyncio.run(_tool("read_paper")(paper_id=paper_id, page=2))

    method, path, kwargs = recorded[0]
    assert (method, path) == ("POST", "paper-page")
    assert kwargs["json"]["paper_id"] == paper_id
    assert kwargs["json"]["page"] == 2


def test_figure_reader_attaches_the_picture_when_the_model_can_see_images(
    monkeypatch,
) -> None:
    _calls(monkeypatch)
    tool = _tool("read_paper_image")
    tool.supports_images = True

    chunk = asyncio.run(tool(paper_id=str(uuid4()), block_id=7))

    images = [block for block in chunk.content if isinstance(block, DataBlock)]
    assert len(images) == 1
    assert base64.b64decode(images[0].source.data) == PNG
    text = next(block for block in chunk.content if isinstance(block, TextBlock))
    assert base64.b64encode(PNG).decode("ascii") not in text.text
    assert "Figure 1" in text.text


def test_figure_reader_returns_captions_only_when_the_model_cannot_see_images(
    monkeypatch,
) -> None:
    _calls(monkeypatch)
    tool = _tool("read_paper_image")
    tool.supports_images = False

    chunk = asyncio.run(tool(paper_id=str(uuid4()), block_id=7))

    assert not [block for block in chunk.content if isinstance(block, DataBlock)]
    text = next(block for block in chunk.content if isinstance(block, TextBlock))
    assert "Figure 1" in text.text
    assert "cannot" in text.text


def test_paper_agent_prefers_search_and_forbids_citing_page_reads() -> None:
    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=object(),
        toolkit=Toolkit(tools=list(tools)),
    )

    prompt = asyncio.run(agent._get_system_prompt())

    assert "Read papers" in prompt
    assert "search_papers" in prompt
    assert "citation" in prompt
    assert "language the user writes in" in prompt


def test_paper_agent_marks_figures_readable_only_when_the_model_sees_images() -> None:
    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    vision = SimpleNamespace(
        formatter=SimpleNamespace(
            supported_input_media_types=["image/*", "text/plain"]
        )
    )

    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=vision,
        toolkit=Toolkit(tools=list(tools)),
    )

    image_tool = next(
        tool
        for group in agent.toolkit.tool_groups
        for tool in group.tools
        if isinstance(tool, PaperImageTool)
    )
    assert image_tool.supports_images is True


def test_paper_agent_keeps_figures_textual_when_the_model_is_text_only() -> None:
    tools = asyncio.run(build_agent_tools(str(uuid4()), "agent", str(uuid4())))
    text_only = SimpleNamespace(
        formatter=SimpleNamespace(
            supported_input_media_types=["text/plain", "application/x-thinking"]
        )
    )

    agent = PaperAgent(
        name="Reader",
        system_prompt="Read papers",
        model=text_only,
        toolkit=Toolkit(tools=list(tools)),
    )

    image_tool = next(
        tool
        for group in agent.toolkit.tool_groups
        for tool in group.tools
        if isinstance(tool, PaperImageTool)
    )
    assert image_tool.supports_images is False
