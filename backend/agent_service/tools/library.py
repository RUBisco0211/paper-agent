"""Read-only tools for the bound paper library."""

from agentscope.tool import ToolBase

from .base import PaperImageTool, PaperReadTool
from .request import business_request


def build_library_tools(user_id: str, session_id: str) -> list[ToolBase]:
    async def list_papers(limit: int = 20, offset: int = 0) -> dict:
        """List papers in this session's authorized library or project scope.

        Each paper includes capabilities: has_fulltext says whether parsing is
        ready, has_keyword_index whether chunks are indexed, and has_embedding
        whether vectors are ready. Check these before searching its evidence.
        """
        return await business_request(
            "GET",
            "papers",
            params={
                "user_id": user_id,
                "session_id": session_id,
                "limit": max(1, min(limit, 50)),
                "offset": max(offset, 0),
            },
        )

    async def search_papers(query: str, limit: int = 8) -> dict:
        """Search paper evidence in this session; returns registered citation IDs.

        The library is indexed with a multilingual embedding model, so query
        in the user's own language and keep technical terms as written. If
        status is degraded, explain that only the available retrieval channel
        contributed; details are English phrases.
        """
        return await business_request(
            "POST",
            "search",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "query": query,
                "limit": max(1, min(limit, 20)),
            },
        )

    async def read_paper(paper_id: str, page: int) -> dict:
        """Read one page of a paper's parsed full text.

        Use this only when a search does not answer the question, when you need
        continuous context around an excerpt, or when the user names a specific
        paper or page. The page text is for understanding: it carries no
        citation ID, so never cite it directly and never invent one. Cite only
        evidence returned by search_papers. Figures on the page are listed with
        their block ids; read one with read_paper_image.
        """
        return await business_request(
            "POST",
            "paper-page",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "paper_id": paper_id,
                "page": page,
            },
        )

    async def read_paper_image(paper_id: str, block_id: int) -> dict:
        """Read one figure or chart that a page read listed.

        Pass the paper id and the block id printed in the page text. You get
        the caption and page, and the picture itself when the current model can
        view images. Read one image at a time unless the user asks for more.
        """
        return await business_request(
            "POST",
            "paper-image",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "paper_id": paper_id,
                "block_id": block_id,
            },
        )

    return [
        PaperReadTool(func, is_read_only=True, is_concurrency_safe=True)
        for func in (list_papers, search_papers, read_paper)
    ] + [
        PaperImageTool(
            read_paper_image, is_read_only=True, is_concurrency_safe=True
        )
    ]
