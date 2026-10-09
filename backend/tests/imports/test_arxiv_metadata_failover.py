import httpx
import pytest

from app.platform.errors import AppError, ErrorCode
from app.scholar.identifiers import parse_identifier
from app.scholar.metadata import ArxivClient


ARXIV_XML = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Recovered Paper</title><author><name>Researcher</name></author>
<summary>Abstract</summary><published>2025-02-01T00:00:00Z</published>
</entry></feed>"""


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_arxiv_metadata_recovers_when_a_rate_limit_clears(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(request.url.host)
        return httpx.Response(429 if len(calls) == 1 else 200, text=ARXIV_XML)

    metadata = ArxivClient(http_client_factory=lambda: _client(respond)).fetch(
        parse_identifier("arXiv:2502.03640")
    )

    assert metadata.title == "Recovered Paper"
    assert calls == ["export.arxiv.org", "export.arxiv.org"]


def test_arxiv_metadata_uses_only_an_exact_openalex_doi_after_rate_limits(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(request.url.host)
        if request.url.host == "export.arxiv.org":
            return httpx.Response(429)
        return httpx.Response(200, json={"results": [{
            "doi": "https://doi.org/10.48550/arXiv.2502.03640",
            "display_name": "Exact Paper",
            "authorships": [{"author": {"display_name": "Researcher"}}],
            "publication_year": 2025,
        }]})

    metadata = ArxivClient(http_client_factory=lambda: _client(respond)).fetch(
        parse_identifier("arXiv:2502.03640")
    )

    assert metadata.source == "openalex"
    assert metadata.title == "Exact Paper"
    assert metadata.arxiv_id == "2502.03640"
    assert calls == ["export.arxiv.org"] * 3 + ["api.openalex.org"]


def test_arxiv_metadata_rejects_a_nonmatching_openalex_result(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)

    def respond(request):
        if request.url.host == "export.arxiv.org":
            return httpx.Response(429)
        return httpx.Response(200, json={"results": [{
            "doi": "https://doi.org/10.48550/arxiv.9999.99999",
            "display_name": "Wrong Paper",
        }]})

    with pytest.raises(AppError) as error:
        ArxivClient(http_client_factory=lambda: _client(respond)).fetch(
            parse_identifier("arXiv:2502.03640")
        )

    assert error.value.code == ErrorCode.PROVIDER_RATE_LIMITED
