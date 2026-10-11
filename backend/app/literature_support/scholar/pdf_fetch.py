"""Downloading publicly available PDFs discovered from metadata.

Only URLs reported by an exact identifier lookup are fetched; arbitrary user
URLs are never crawled.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog

from app.platform.errors import AppError, ErrorCode
from app.platform.outbound_http import HttpClientFactory, default_http_client_factory

logger = structlog.get_logger(__name__)

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class DownloadedPdf:
    path: Path
    byte_size: int


class PdfFetcher:
    """Stream a PDF from an allow-listed metadata source into a temp file."""

    def __init__(
        self,
        *,
        http_client_factory: HttpClientFactory = default_http_client_factory,
        max_bytes: int,
    ) -> None:
        self._client_factory = http_client_factory
        self._max_bytes = max_bytes

    def download(self, url: str, *, destination: Path) -> DownloadedPdf:
        size = 0
        try:
            with (
                self._client_factory() as client,
                client.stream("GET", url) as response,
            ):
                if response.status_code == 404:
                    raise AppError(
                        "来源没有提供可下载的 PDF",
                        code=ErrorCode.PAPER_PDF_NOT_AVAILABLE,
                        status_code=422,
                    )
                if response.status_code >= 400:
                    raise AppError(
                        "下载 PDF 失败",
                        code=ErrorCode.PROVIDER_UNAVAILABLE,
                        status_code=502,
                    )
                with destination.open("wb") as handle:
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        size += len(chunk)
                        if size > self._max_bytes:
                            handle.close()
                            destination.unlink(missing_ok=True)
                            raise AppError(
                                "PDF 超过大小上限",
                                code=ErrorCode.PDF_TOO_LARGE,
                                status_code=413,
                            )
                        handle.write(chunk)
        except httpx.TimeoutException as exc:
            raise AppError(
                "下载 PDF 超时",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "无法连接 PDF 来源",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=502,
            ) from exc

        logger.info("scholar.pdf.downloaded", byte_size=size)
        return DownloadedPdf(path=destination, byte_size=size)


def pdf_fetcher_factory(max_bytes: int) -> Callable[[], PdfFetcher]:
    return lambda: PdfFetcher(max_bytes=max_bytes)
