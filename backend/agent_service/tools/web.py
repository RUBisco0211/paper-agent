"""Read and search the public web on the user's behalf.

Both reads leave the business service in charge of credentials and caching, so
this module never holds a secret or a Redis handle of its own. Failures come
back as ordinary tool results carrying a stable code and an actionable message,
so the agent can tell the user what to do instead of retrying blindly.
"""

import httpx
from agentscope.tool import ToolBase

from .base import PaperReadTool
from .request import BusinessRequestFailed, business_request


def build_web_tools(user_id: str) -> list[ToolBase]:
    async def web_search(query: str, max_results: int = 5) -> dict:
        """Search the public web for background, terminology, or paper identities.

        Use this when the user names something you cannot place from the
        library alone, such as an acronym or a method name, and you need to
        find out what it refers to. Each result is a title, a URL and a short
        snippet, and none of them carries a citation identifier.
        """
        return await _call(
            "web_search",
            "web-search",
            {
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

        Start with offset 0 and keep passing back the returned next_offset until
        truncated is false. Do not compute offsets yourself: an offset at or past
        total_chars comes back with offset_out_of_range true and empty content,
        which means the offset was wrong, not that the page has no more text.
        """
        return await _call(
            "web_fetch",
            "web-fetch",
            {
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
        return await _call(
            "web_extract_excerpt",
            "web-extract-excerpt",
            {
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


async def _call(
    tool: str,
    path: str,
    payload: dict,
) -> dict:
    try:
        return await business_request("POST", path, json=payload)
    except BusinessRequestFailed as exc:
        return {
            "status": "error",
            "code": exc.code,
            "message": exc.message,
            "tool": tool,
        }
    except (httpx.HTTPError, RuntimeError):
        return {
            "status": "error",
            "code": "provider_unavailable",
            "message": "upstream unavailable",
            "tool": tool,
        }


__all__ = ["build_web_tools"]
