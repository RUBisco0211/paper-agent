import httpx
import pytest

from app.platform.errors import AppError, ErrorCode
from app.scholar.pdf_sources import DoiPdfLocator


def test_pdf_locator_returns_only_urls_from_exact_doi_matches() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "api.openalex.org":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "doi": "https://doi.org/10.1234/other",
                            "best_oa_location": {
                                "pdf_url": "https://wrong.example/pdf"
                            },
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "externalIds": {"DOI": "10.1234/open"},
                "openAccessPdf": {"url": "https://papers.example/open.pdf"},
            },
        )

    locator = DoiPdfLocator(
        http_client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(handle),
        )
    )

    assert locator.find("10.1234/open") == ["https://papers.example/open.pdf"]
    assert requests[0].url.params["filter"] == "doi:https://doi.org/10.1234/open"
    assert requests[1].url.path.endswith("/DOI:10.1234/open")


def test_pdf_locator_rejects_non_public_or_non_https_pdf_urls() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openalex.org":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "doi": "https://doi.org/10.1234/open",
                            "best_oa_location": {
                                "pdf_url": "http://papers.example/open.pdf"
                            },
                            "locations": [
                                {"is_oa": True, "pdf_url": "https://127.0.0.1/file"}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "externalIds": {"DOI": "10.1234/open"},
                "openAccessPdf": {"url": "https://papers.example/open.pdf"},
            },
        )

    locator = DoiPdfLocator(
        http_client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(handle),
        )
    )

    assert locator.find("10.1234/open") == ["https://papers.example/open.pdf"]


def test_pdf_locator_reports_unavailable_when_both_sources_fail() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    locator = DoiPdfLocator(
        http_client_factory=lambda: httpx.Client(
            transport=httpx.MockTransport(handle),
        )
    )

    with pytest.raises(AppError) as error:
        locator.find("10.1234/open")

    assert error.value.code == ErrorCode.PROVIDER_UNAVAILABLE
