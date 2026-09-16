"""Untrusted-input validation for uploaded PDFs."""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..platform.errors import AppError, ErrorCode
from .domain import PDF_MAGIC


@dataclass(frozen=True, slots=True)
class PdfInspection:
    page_count: int


def ensure_pdf_magic(first_bytes: bytes) -> None:
    if not first_bytes.startswith(PDF_MAGIC):
        raise AppError(
            "文件不是有效的 PDF",
            code=ErrorCode.PDF_INVALID,
            status_code=415,
        )


def inspect_pdf(path: Path, *, max_pages: int) -> PdfInspection:
    """Read just enough structure to trust the file for processing."""
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise AppError(
                "不支持加密 PDF",
                code=ErrorCode.PDF_ENCRYPTED,
                status_code=422,
            )
        page_count = len(reader.pages)
    except AppError:
        raise
    except (PdfReadError, ValueError, OSError, KeyError) as exc:
        raise AppError(
            "PDF 无法读取或已损坏",
            code=ErrorCode.PDF_UNREADABLE,
            status_code=422,
        ) from exc

    if page_count == 0:
        raise AppError(
            "PDF 不包含任何页面",
            code=ErrorCode.PDF_UNREADABLE,
            status_code=422,
        )
    if page_count > max_pages:
        raise AppError(
            f"PDF 页数超过上限（{max_pages} 页）",
            code=ErrorCode.PDF_TOO_MANY_PAGES,
            status_code=422,
        )
    return PdfInspection(page_count=page_count)
