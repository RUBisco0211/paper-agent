"""Small, bounded OpenAlex Works client for candidate discovery."""

import httpx

from .config import settings
from .errors import AppError, ErrorCode, ProviderUnavailableError


class OpenAlexAdapter:
    def search(self, query: str, limit: int) -> list[dict]:
        headers = {"Accept": "application/json"}
        key = settings.openalex_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            with httpx.Client(timeout=settings.outbound_timeout_seconds) as client:
                response = client.get(
                    "https://api.openalex.org/works",
                    params={"search": query, "per_page": limit},
                    headers=headers,
                )
                if response.status_code == 429:
                    raise AppError(
                        "文献发现服务请求过于频繁",
                        code=ErrorCode.PROVIDER_RATE_LIMITED,
                        status_code=429,
                    )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderUnavailableError("文献发现服务暂时不可用") from exc

        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise ProviderUnavailableError("文献发现服务返回无效结果")
        papers = []
        for item in results[:limit]:
            if not isinstance(item, dict):
                continue
            location = item.get("primary_location") or {}
            if not isinstance(location, dict):
                location = {}
            authorships = item.get("authorships") or []
            if not isinstance(authorships, list):
                authorships = []
            doi = item.get("doi")
            if isinstance(doi, str) and doi.startswith("https://doi.org/"):
                doi = doi.removeprefix("https://doi.org/")
            papers.append(
                {
                    "openalex_id": item.get("id"),
                    "title": (item.get("display_name") or "")[:500],
                    "doi": doi,
                    "year": item.get("publication_year"),
                    "authors": [
                        author["author"]["display_name"][:120]
                        for author in authorships[:8]
                        if isinstance(author, dict)
                        and isinstance(author.get("author"), dict)
                        and isinstance(author["author"].get("display_name"), str)
                    ],
                    "url": location.get("landing_page_url")
                    or item.get("doi")
                    or item.get("id"),
                }
            )
        return papers
