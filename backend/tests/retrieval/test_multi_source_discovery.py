import httpx

from app.platform import discovery
from app.platform.discovery import DiscoveryAggregator


class Source:
    def __init__(self, name, papers=None, error=None):
        self.name, self.papers, self.error = name, papers or [], error

    def search(self, query, limit):
        if self.error:
            raise self.error
        return self.papers


def test_discovery_merges_identifier_matches_and_keeps_pdf_when_sources_overlap():
    aggregator = DiscoveryAggregator(
        [
            Source(
                "openalex",
                [
                    {
                        "source_id": "https://openalex.org/W1",
                        "title": "Paper",
                        "doi": "10.1234/x",
                        "pdf_url": None,
                    }
                ],
            ),
            Source(
                "semantic_scholar",
                [
                    {
                        "source_id": "https://www.semanticscholar.org/paper/abc",
                        "title": "Paper",
                        "doi": "10.1234/x",
                        "pdf_url": "https://example.org/x.pdf",
                    }
                ],
            ),
        ]
    )
    result = aggregator.search("Paper", 8)
    assert len(result.papers) == 1
    assert result.papers[0]["pdf_url"] == "https://example.org/x.pdf"
    assert result.papers[0]["sources"] == ["openalex", "semantic_scholar"]


def test_discovery_keeps_same_title_without_identifiers_as_separate_candidates():
    result = DiscoveryAggregator(
        [
            Source(
                "openalex", [{"source_id": "https://openalex.org/W1", "title": "Same"}]
            ),
            Source(
                "crossref",
                [{"source_id": "https://doi.org/10.1234/y", "title": "Same"}],
            ),
        ]
    ).search("Same", 8)
    assert len(result.papers) == 2


def test_discovery_includes_other_sources_when_first_source_fills_limit():
    result = DiscoveryAggregator(
        [
            Source(
                "openalex",
                [
                    {
                        "source_id": f"https://openalex.org/W{i}",
                        "title": f"OpenAlex {i}",
                    }
                    for i in range(3)
                ],
            ),
            Source(
                "semantic_scholar",
                [
                    {
                        "source_id": "https://www.semanticscholar.org/paper/unique",
                        "title": "Unique",
                    }
                ],
            ),
        ]
    ).search("query", 3)
    assert any(paper["title"] == "Unique" for paper in result.papers)


def test_discovery_reports_one_failed_source_without_dropping_other_results():
    result = DiscoveryAggregator(
        [
            Source("openalex", error=RuntimeError("rate limited")),
            Source(
                "crossref",
                [{"source_id": "https://doi.org/10.1234/y", "title": "Other"}],
            ),
        ]
    ).search("Other", 8)
    assert len(result.papers) == 1
    assert result.failed_sources == ["openalex"]


def test_semantic_scholar_exposes_open_access_pdf_and_doi(monkeypatch):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "data": [
                    {
                        "paperId": "abc",
                        "title": "Paper",
                        "year": 2026,
                        "externalIds": {"DOI": "10.1234/paper"},
                        "authors": [],
                        "openAccessPdf": {"url": "https://example.org/paper.pdf"},
                    }
                ]
            },
        )
    )
    original = httpx.Client
    monkeypatch.setattr(
        discovery.httpx,
        "Client",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    paper = discovery.SemanticScholarAdapter().search("Paper", 1)[0]
    assert paper["doi"] == "10.1234/paper"
    assert paper["pdf_url"] == "https://example.org/paper.pdf"


def test_crossref_exposes_doi_without_claiming_pdf_availability(monkeypatch):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "DOI": "10.1234/paper",
                            "title": ["Paper"],
                            "published": {"date-parts": [[2026]]},
                            "author": [],
                        }
                    ]
                }
            },
        )
    )
    original = httpx.Client
    monkeypatch.setattr(
        discovery.httpx,
        "Client",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    paper = discovery.CrossrefAdapter().search("Paper", 1)[0]
    assert paper["doi"] == "10.1234/paper"
    assert paper["pdf_url"] is None
