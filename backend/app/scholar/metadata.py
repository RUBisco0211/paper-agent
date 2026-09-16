"""Online metadata completion for known identifiers.

Only exact identifier lookups are implemented (Crossref for DOIs, the arXiv
Atom API for arXiv ids). Title search is deliberately not part of this module:
candidates from a search must not be treated as the confirmed paper.
"""

import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

import httpx
import structlog

from ..library.domain import MetadataStatus, PaperSource
from ..platform.config import settings
from ..platform.errors import AppError, ErrorCode
from .identifiers import Identifier, IdentifierType

logger = structlog.get_logger(__name__)

ARXIV_NAMESPACE = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_JATS_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Bibliographic fields as reported by one source."""

    source: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    venue: str | None = None
    pdf_url: str | None = None
    extra: dict | None = None

    @property
    def is_complete(self) -> bool:
        return bool(self.title and self.authors)

    def bibliographic(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "year": self.year,
            "venue": self.venue,
            "source": self.source,
            "extra": self.extra or {},
        }

    def metadata_status(self) -> MetadataStatus:
        if self.is_complete:
            return MetadataStatus.RECOGNIZED
        if self.title or self.authors:
            return MetadataStatus.PARTIAL
        return MetadataStatus.UNRECOGNIZED


@dataclass(frozen=True, slots=True)
class ResolutionOutcome:
    """Result of a best-effort online completion."""

    status: MetadataStatus
    metadata: ProviderMetadata | None = None
    source: str | None = None
    error_code: ErrorCode | None = None


class MetadataProvider(Protocol):
    name: str

    def supports(self, identifier: Identifier) -> bool: ...

    def fetch(self, identifier: Identifier) -> ProviderMetadata: ...


HttpClientFactory = Callable[[], httpx.Client]


def default_http_client_factory() -> httpx.Client:
    return httpx.Client(
        timeout=settings.outbound_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "paper-agent/0.1 (metadata resolution)"},
    )


class CrossrefClient:
    """Crossref REST API lookup for DOIs."""

    name = "crossref"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        http_client_factory: HttpClientFactory = default_http_client_factory,
    ) -> None:
        self._base_url = (base_url or settings.crossref_api_url).rstrip("/")
        self._client_factory = http_client_factory

    def supports(self, identifier: Identifier) -> bool:
        return identifier.type is IdentifierType.DOI

    def fetch(self, identifier: Identifier) -> ProviderMetadata:
        with self._client_factory() as client:
            response = _request(
                client,
                f"{self._base_url}/works/{identifier.value}",
            )
        message = response.json().get("message", {})
        return _crossref_metadata(message, identifier)


class ArxivClient:
    """arXiv Atom API lookup for arXiv identifiers."""

    name = "arxiv"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        pdf_base_url: str | None = None,
        http_client_factory: HttpClientFactory = default_http_client_factory,
    ) -> None:
        self._base_url = base_url or settings.arxiv_api_url
        self._pdf_base_url = (pdf_base_url or settings.arxiv_pdf_url).rstrip("/")
        self._client_factory = http_client_factory

    def supports(self, identifier: Identifier) -> bool:
        return identifier.type is IdentifierType.ARXIV

    def fetch(self, identifier: Identifier) -> ProviderMetadata:
        with self._client_factory() as client:
            response = _request(
                client,
                self._base_url,
                params={"id_list": identifier.value},
            )
        return _arxiv_metadata(
            response.text,
            identifier,
            pdf_url=f"{self._pdf_base_url}/{identifier.value}",
        )


class MetadataResolver:
    """Exact identifier lookup with best-effort failure semantics."""

    def __init__(self, providers: Sequence[MetadataProvider]) -> None:
        self._providers = list(providers)

    def resolve(self, identifier: Identifier) -> ResolutionOutcome:
        provider = next(
            (item for item in self._providers if item.supports(identifier)),
            None,
        )
        if provider is None:
            return ResolutionOutcome(
                status=MetadataStatus.UNRECOGNIZED,
                error_code=ErrorCode.PROVIDER_NOT_CONFIGURED,
            )
        try:
            metadata = provider.fetch(identifier)
        except AppError as exc:
            logger.info(
                "scholar.metadata.provider_failed",
                source=provider.name,
                error_code=str(exc.code),
            )
            return ResolutionOutcome(
                status=MetadataStatus.PROVIDER_FAILED,
                source=provider.name,
                error_code=exc.code,
            )
        return ResolutionOutcome(
            status=metadata.metadata_status(),
            metadata=metadata,
            source=provider.name,
        )


def _request(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
) -> httpx.Response:
    try:
        response = client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise AppError(
            "元数据服务响应超时",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            "无法连接元数据服务",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=502,
        ) from exc

    if response.status_code == 404:
        raise AppError(
            "没有查询到该标识符对应的论文",
            code=ErrorCode.METADATA_NOT_FOUND,
            status_code=404,
        )
    if response.status_code == 429:
        raise AppError(
            "元数据服务限流，请稍后重试",
            code=ErrorCode.PROVIDER_RATE_LIMITED,
            status_code=429,
        )
    if response.status_code >= 500:
        raise AppError(
            "元数据服务暂时不可用",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=502,
        )
    if response.status_code >= 400:
        raise AppError(
            "元数据查询被拒绝",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=502,
        )
    return response


def _crossref_metadata(message: dict, identifier: Identifier) -> ProviderMetadata:
    authors = [
        _format_author(author.get("given"), author.get("family") or author.get("name"))
        for author in message.get("author", [])
    ]
    pdf_url = next(
        (
            link.get("URL")
            for link in message.get("link", [])
            if link.get("content-type") == "application/pdf"
        ),
        None,
    )
    return ProviderMetadata(
        source=CrossrefClient.name,
        title=_first(message.get("title")),
        authors=[author for author in authors if author],
        abstract=_strip_markup(message.get("abstract")),
        doi=message.get("DOI") or identifier.value,
        year=_crossref_year(message),
        venue=_first(message.get("container-title")),
        pdf_url=pdf_url,
        extra={
            "type": message.get("type"),
            "publisher": message.get("publisher"),
            "reference_count": message.get("reference-count"),
        },
    )


def _arxiv_metadata(
    payload: str,
    identifier: Identifier,
    *,
    pdf_url: str,
) -> ProviderMetadata:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise AppError(
            "arXiv 返回内容无法解析",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=502,
        ) from exc

    entry = root.find("atom:entry", ARXIV_NAMESPACE)
    if entry is None:
        raise AppError(
            "没有查询到该 arXiv 标识符对应的论文",
            code=ErrorCode.METADATA_NOT_FOUND,
            status_code=404,
        )

    published = _text(entry, "atom:published")
    doi = _text(entry, "arxiv:doi")
    return ProviderMetadata(
        source=ArxivClient.name,
        title=_collapse(_text(entry, "atom:title")),
        authors=[
            _collapse(_text(author, "atom:name"))
            for author in entry.findall("atom:author", ARXIV_NAMESPACE)
        ],
        abstract=_collapse(_text(entry, "atom:summary")),
        doi=doi,
        arxiv_id=identifier.value,
        year=int(published[:4]) if published[:4].isdigit() else None,
        venue=_text(entry, "arxiv:journal_ref"),
        pdf_url=pdf_url,
        extra={"primary_category": _arxiv_primary_category(entry)},
    )


def _arxiv_primary_category(entry: ElementTree.Element) -> str | None:
    category = entry.find("arxiv:primary_category", ARXIV_NAMESPACE)
    if category is None:
        return None
    return category.get("term")


def _first(values: list | None) -> str | None:
    if not values:
        return None
    return values[0]


def _crossref_year(message: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def _format_author(given: str | None, family: str | None) -> str:
    return " ".join(part for part in (given, family) if part).strip()


def _strip_markup(value: str | None) -> str | None:
    if not value:
        return None
    return _collapse(_JATS_TAG.sub(" ", value))


def _collapse(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _text(element: ElementTree.Element, path: str) -> str | None:
    found = element.find(path, ARXIV_NAMESPACE)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def build_default_resolver() -> MetadataResolver:
    return MetadataResolver([CrossrefClient(), ArxivClient()])


def source_for(identifier: Identifier) -> PaperSource:
    return (
        PaperSource.DOI if identifier.type is IdentifierType.DOI else PaperSource.ARXIV
    )
