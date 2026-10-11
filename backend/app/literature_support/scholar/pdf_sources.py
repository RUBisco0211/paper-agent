"""Find publicly listed PDF URLs for an exact DOI during import."""

import ipaddress
from collections.abc import Callable
from urllib.parse import quote, urlsplit

import httpx
import structlog

from app.platform.config import settings
from app.platform.errors import AppError, ErrorCode
from app.platform.outbound_http import default_http_client_factory

logger = structlog.get_logger(__name__)


def _public_https_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".local"):
        return None
    try:
        if not ipaddress.ip_address(host).is_global:
            return None
    except ValueError:
        pass
    return value


class DoiPdfLocator:
    """Query OpenAlex and Semantic Scholar by DOI, never by title or supplied URL."""

    def __init__(
        self,
        *,
        http_client_factory: Callable[[], httpx.Client] = default_http_client_factory,
    ) -> None:
        self._client_factory = http_client_factory

    def find(self, doi: str) -> list[str]:
        urls: list[str] = []
        failures = 0
        for name, lookup in (
            ("openalex", self._openalex),
            ("semantic_scholar", self._semantic_scholar),
        ):
            try:
                urls.extend(lookup(doi))
            except (
                httpx.HTTPError,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
            ) as exc:
                failures += 1
                logger.warning(
                    "scholar.pdf_source.lookup_failed",
                    source=name,
                    error_type=type(exc).__name__,
                )
        unique = list(dict.fromkeys(urls))
        if not unique and failures:
            raise AppError(
                "开放 PDF 来源暂时不可用",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=502,
            )
        return unique

    def _openalex(self, doi: str) -> list[str]:
        headers = {"Accept": "application/json"}
        key = settings.openalex_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with self._client_factory() as client:
            response = client.get(
                "https://api.openalex.org/works",
                params={"filter": f"doi:https://doi.org/{doi}", "per_page": 1},
                headers=headers,
            )
            response.raise_for_status()
            items = response.json().get("results") or []
        if not items:
            return []
        work = items[0]
        if (work.get("doi") or "").lower() != f"https://doi.org/{doi}".lower():
            return []
        locations = [work.get("best_oa_location") or {}]
        locations.extend(
            item for item in (work.get("locations") or []) if item.get("is_oa")
        )
        return [
            url
            for location in locations
            if (url := _public_https_url(location.get("pdf_url")))
        ]

    def _semantic_scholar(self, doi: str) -> list[str]:
        encoded = quote(f"DOI:{doi}", safe=":")
        with self._client_factory() as client:
            response = client.get(
                f"https://api.semanticscholar.org/graph/v1/paper/{encoded}",
                params={"fields": "externalIds,openAccessPdf"},
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            paper = response.json()
        ids = paper.get("externalIds") or {}
        if (ids.get("DOI") or "").lower() != doi.lower():
            return []
        url = _public_https_url((paper.get("openAccessPdf") or {}).get("url"))
        return [url] if url else []
