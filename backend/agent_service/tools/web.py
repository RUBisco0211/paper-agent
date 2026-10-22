"""Read and search the public web on the user's behalf.

Both reads leave the business service in charge of credentials and caching, so
this module never holds a secret or a Redis handle of its own.
"""

from agentscope.tool import ToolBase

from .base import PaperReadTool
from .request import business_request


def build_web_tools(user_id: str) -> list[ToolBase]:
    async def web_search(query: str, max_results: int = 5) -> dict:
        """Search the public web for background, terminology, or paper identities.

        Use this when the user names something you cannot place from the
        library alone, such as an acronym or a method name, and you need to
        find out what it refers to. Each result is a title, a URL and a short
        snippet, and none of them carries a citation identifier.
        """
        return await business_request(
            "POST",
            "web-search",
            json={
                "user_id": user_id,
                "query": query,
                "max_results": max(1, min(max_results, 10)),
            },
        )

    async def web_fetch(
        url: str,
        offset: int = 0,
        max_chars: int = 8000,
    ) -> dict:
        """Read one web page as text.

        Long pages come back in windows. When the result says it was truncated,
        call again with the returned next_offset to read the continuation.
        """
        return await business_request(
            "POST",
            "web-fetch",
            json={
                "user_id": user_id,
                "url": url,
                "offset": max(0, offset),
                "max_chars": max(1, min(max_chars, 20000)),
            },
        )

    async def web_extract_excerpt(url: str, query: str, chunks: int = 3) -> dict:
        """Read only the parts of a web page that answer one question.

        Use this instead of web_fetch when a page is long and the question is
        narrow; the returned text is assembled from passages chosen for it.
        """
        return await business_request(
            "POST",
            "web-extract-excerpt",
            json={
                "user_id": user_id,
                "url": url,
                "query": query,
                "chunks": max(1, min(chunks, 5)),
            },
        )

    return [
        PaperReadTool(func, is_read_only=True, is_concurrency_safe=True)
        for func in (web_search, web_fetch, web_extract_excerpt)
    ]
