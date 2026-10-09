from pathlib import Path

from fastapi.testclient import TestClient

from app.imports.depends import get_pdf_locator
from app.library.depends import get_metadata_resolver, get_pdf_fetcher
from app.platform.errors import AppError, ErrorCode
from app.scholar.metadata import MetadataResolver, ProviderMetadata
from tests.conftest import auth_headers
from tests.library.test_pdf_and_metadata import FakePdfFetcher, FakeProvider


class FakeLocator:
    def find(self, doi: str) -> list[str]:
        assert doi == "10.1234/open"
        return ["https://example.org/open.pdf"]


class FailingFirstFetcher(FakePdfFetcher):
    def download(self, url: str, *, destination: Path):
        if url == "https://publisher.example/blocked.pdf":
            self.urls.append(url)
            raise AppError(
                "PDF unavailable",
                code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                status_code=422,
            )
        return super().download(url, destination=destination)


def test_doi_import_downloads_an_open_pdf_when_crossref_has_no_pdf_link(
    client: TestClient, api_prefix: str, register_user, make_pdf
) -> None:
    provider = FakeProvider(
        ProviderMetadata(
            source="crossref",
            title="Open paper",
            authors=["A. Author"],
            doi="10.1234/open",
            pdf_url=None,
        )
    )
    fetcher = FakePdfFetcher(make_pdf())
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: fetcher
    client.app.dependency_overrides[get_pdf_locator] = FakeLocator
    token = register_user(email="doi-fallback@example.com")["access_token"]

    result = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": "10.1234/open"},
    )

    assert result.status_code == 202
    assert result.json()["status"] == "ready"
    assert fetcher.urls == ["https://example.org/open.pdf"]


def test_doi_import_tries_an_open_pdf_when_the_publisher_pdf_fails(
    client: TestClient, api_prefix: str, register_user, make_pdf
) -> None:
    provider = FakeProvider(
        ProviderMetadata(
            source="crossref",
            title="Open paper",
            authors=["A. Author"],
            doi="10.1234/open",
            pdf_url="https://publisher.example/blocked.pdf",
        )
    )
    fetcher = FailingFirstFetcher(make_pdf())
    client.app.dependency_overrides[get_metadata_resolver] = lambda: MetadataResolver(
        [provider]
    )
    client.app.dependency_overrides[get_pdf_fetcher] = lambda: fetcher
    client.app.dependency_overrides[get_pdf_locator] = FakeLocator
    token = register_user(email="doi-publisher-fallback@example.com")["access_token"]

    result = client.post(
        f"{api_prefix}/imports",
        headers=auth_headers(token),
        json={"identifier": "10.1234/open"},
    )

    assert result.status_code == 202
    assert result.json()["status"] == "ready"
    assert fetcher.urls == [
        "https://publisher.example/blocked.pdf",
        "https://example.org/open.pdf",
    ]
