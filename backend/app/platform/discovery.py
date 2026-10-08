"""Bounded multi-source scholarly candidate discovery."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import httpx

from .config import settings
from .errors import AppError, ProviderUnavailableError
from .openalex import OpenAlexAdapter


def _doi(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = (
        value.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    )
    return value if value.lower().startswith("10.") else None


def _https(value: object) -> str | None:
    return value if isinstance(value, str) and value.startswith("https://") else None


class SemanticScholarAdapter:
    name = "semantic_scholar"

    def search(self, query: str, limit: int) -> list[dict]:
        with httpx.Client(timeout=settings.outbound_timeout_seconds) as client:
            response = client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": query,
                    "limit": limit,
                    "fields": "title,year,authors,externalIds,url,openAccessPdf",
                },
            )
            response.raise_for_status()
            data = response.json()
        papers = []
        for item in data.get("data", [])[:limit]:
            ids = item.get("externalIds") or {}
            paper_id = item.get("paperId")
            if not paper_id:
                continue
            pdf = item.get("openAccessPdf") or {}
            papers.append(
                {
                    "source_id": f"https://www.semanticscholar.org/paper/{paper_id}",
                    "title": (item.get("title") or "")[:500],
                    "doi": _doi(ids.get("DOI")),
                    "arxiv_id": ids.get("ArXiv"),
                    "year": item.get("year"),
                    "authors": [
                        a["name"][:120]
                        for a in (item.get("authors") or [])[:8]
                        if isinstance(a.get("name"), str)
                    ],
                    "url": _https(item.get("url")),
                    "pdf_url": _https(pdf.get("url")),
                }
            )
        return papers


class CrossrefAdapter:
    name = "crossref"

    def search(self, query: str, limit: int) -> list[dict]:
        with httpx.Client(timeout=settings.outbound_timeout_seconds) as client:
            response = client.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": query, "rows": limit},
                headers={"User-Agent": "PaperAgent/1.0 (scholarly discovery)"},
            )
            response.raise_for_status()
            data = response.json()
        papers = []
        for item in data.get("message", {}).get("items", [])[:limit]:
            doi = _doi(item.get("DOI"))
            if not doi:
                continue
            date_parts = (item.get("published") or {}).get("date-parts") or []
            authors = item.get("author") or []
            papers.append(
                {
                    "source_id": f"https://doi.org/{doi}",
                    "title": ((item.get("title") or [""])[0] or "")[:500],
                    "doi": doi,
                    "year": date_parts[0][0] if date_parts and date_parts[0] else None,
                    "authors": [
                        " ".join(filter(None, (a.get("given"), a.get("family"))))[:120]
                        for a in authors[:8]
                    ],
                    "url": f"https://doi.org/{doi}",
                    "pdf_url": None,
                }
            )
        return papers


@dataclass
class DiscoveryResult:
    papers: list[dict]
    failed_sources: list[str]


class DiscoveryAggregator:
    def __init__(self, sources: list | None = None) -> None:
        self.sources = (
            sources
            if sources is not None
            else [OpenAlexAdapter(), SemanticScholarAdapter(), CrossrefAdapter()]
        )

    def search(self, query: str, limit: int) -> DiscoveryResult:
        hits: dict[str, list[dict]] = {}
        failed: list[str] = []
        with ThreadPoolExecutor(max_workers=len(self.sources)) as executor:
            futures = {
                executor.submit(source.search, query, limit): source.name
                for source in self.sources
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    hits[name] = future.result()
                except (
                    AppError,
                    httpx.HTTPError,
                    ValueError,
                    KeyError,
                    TypeError,
                    RuntimeError,
                    AttributeError,
                ):
                    failed.append(name)
        if len(failed) == len(self.sources):
            raise ProviderUnavailableError("文献发现服务暂时不可用")
        papers: list[dict] = []
        by_identifier: dict[str, dict] = {}
        ranked_hits = [
            (source, items[rank])
            for rank in range(max((len(items) for items in hits.values()), default=0))
            for source in self.sources
            if rank < len(items := hits.get(source.name, []))
        ]
        for source, item in ranked_hits:
            doi = _doi(item.get("doi"))
            arxiv_id = item.get("arxiv_id")
            keys = ([f"doi:{doi.lower()}"] if doi else []) + (
                [f"arxiv:{str(arxiv_id).lower()}"] if arxiv_id else []
            )
            existing = next(
                (by_identifier[key] for key in keys if key in by_identifier), None
            )
            if existing is None:
                existing = {**item, "sources": [source.name]}
                papers.append(existing)
            else:
                if source.name not in existing["sources"]:
                    existing["sources"].append(source.name)
                for field in (
                    "doi",
                    "arxiv_id",
                    "pdf_url",
                    "url",
                    "year",
                    "authors",
                ):
                    if not existing.get(field) and item.get(field):
                        existing[field] = item[field]
            for key in keys:
                by_identifier[key] = existing
        return DiscoveryResult(papers=papers[:limit], failed_sources=sorted(failed))
