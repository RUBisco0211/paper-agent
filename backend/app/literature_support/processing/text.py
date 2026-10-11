"""Lightweight local text extraction from PDF front matter.

The first version does not run OCR and does not build a layout index: it reads
plain text from the leading pages so identifiers can be recognized before any
online lookup. Full-text parsing stays with the MinerU stage.
"""

from pathlib import Path

import structlog
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.literature_support.scholar.identifiers import Identifier, find_identifiers
from app.platform.errors import AppError, ErrorCode

logger = structlog.get_logger(__name__)

FRONT_MATTER_PAGES = 5
MAX_CHARS = 200_000


def extract_front_matter_text(path: Path, *, pages: int = FRONT_MATTER_PAGES) -> str:
    """Return plain text of the first ``pages`` pages, best effort."""
    try:
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages[:pages]:
            chunks.append(page.extract_text() or "")
            if sum(len(chunk) for chunk in chunks) > MAX_CHARS:
                break
    except (PdfReadError, ValueError, OSError, KeyError) as exc:
        raise AppError(
            "无法读取 PDF 文本层",
            code=ErrorCode.PDF_UNREADABLE,
            status_code=422,
        ) from exc
    return "\n".join(chunks)


def detect_identifiers(path: Path) -> list[Identifier]:
    """Best-effort identifiers found in the PDF front matter."""
    try:
        text = extract_front_matter_text(path)
    except AppError:
        logger.info("library.identifier_scan.skipped", reason="text_unavailable")
        return []
    identifiers = find_identifiers(text)
    logger.debug(
        "library.identifier_scan.completed",
        identifier_count=len(identifiers),
    )
    return identifiers
