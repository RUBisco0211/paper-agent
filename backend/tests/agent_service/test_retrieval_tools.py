import asyncio
from uuid import uuid4

from agent_service.retrieval_tools import build_retrieval_tools


def test_agent_tools_expose_four_reads_and_one_approved_write_when_built() -> None:
    tools = asyncio.run(build_retrieval_tools(str(uuid4()), "agent", str(uuid4())))

    assert {tool.name for tool in tools} == {
        "list_papers",
        "search_papers",
        "get_paper_excerpt",
        "discover_papers",
        "import_selected_papers",
    }
    assert sum(not tool.is_read_only for tool in tools) == 1
    assert all("scope" not in str(tool.input_schema) for tool in tools)
