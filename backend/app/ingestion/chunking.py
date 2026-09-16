"""Merging-style chunking over MinerU ``content_list.json``.

Blocks are accumulated in document order until a size budget is hit, keeping the
heading path, page range and source block ids so evidence can be traced back to
the original paper.
"""

import re
from dataclasses import dataclass, field

from ..retrieval.domain import ChunkDraft

CHARS_PER_TOKEN = 4
HEADING_TYPES = {"title", "heading"}
MAX_TITLE_LEVEL = 3
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class _Buffer:
    texts: list[str] = field(default_factory=list)
    block_ids: list[int] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    title_path: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(part for part in self.texts if part)

    @property
    def is_empty(self) -> bool:
        return not self.text

    def clear(self) -> None:
        self.texts.clear()
        self.block_ids.clear()
        self.page_start = None
        self.page_end = None


def build_chunks(
    content_list: list[dict],
    *,
    target_tokens: int = 512,
    max_chars: int = 4000,
) -> list[ChunkDraft]:
    """Turn MinerU blocks into retrievable chunks."""
    drafts: list[ChunkDraft] = []
    headings: list[str] = []
    buffer = _Buffer()
    index = 0

    def _close() -> None:
        nonlocal index
        if buffer.is_empty:
            buffer.clear()
            return
        text = buffer.text
        for piece in _split_oversized(text, max_chars=max_chars):
            drafts.append(
                ChunkDraft(
                    chunk_index=index,
                    content=piece,
                    title_path=buffer.title_path,
                    page_start=buffer.page_start,
                    page_end=buffer.page_end,
                    block_ids=list(buffer.block_ids),
                    chunk_metadata={"char_count": len(piece)},
                ),
            )
            index += 1
        buffer.clear()

    for block_id, block in enumerate(content_list):
        if not isinstance(block, dict):
            continue
        page = _page_number(block)
        text = _block_text(block)
        if _is_heading(block):
            title = (block.get("text") or "").strip()
            if title:
                level = int(block.get("text_level") or 1)
                headings = [*headings[: max(level - 1, 0)], title]
                if (
                    not buffer.is_empty
                    and _estimated_tokens(buffer.text) >= target_tokens // 2
                ):
                    _close()
            if text:
                buffer.texts.append(text)
                buffer.block_ids.append(block_id)
                buffer.page_start, buffer.page_end = _page_range(
                    buffer.page_start,
                    buffer.page_end,
                    page,
                )
            buffer.title_path = " > ".join(headings) or None
            continue

        if not text:
            continue
        buffer.title_path = buffer.title_path or (" > ".join(headings) or None)
        buffer.texts.append(text)
        buffer.block_ids.append(block_id)
        buffer.page_start, buffer.page_end = _page_range(
            buffer.page_start,
            buffer.page_end,
            page,
        )

        if (
            _estimated_tokens(buffer.text) >= target_tokens
            or len(buffer.text) >= max_chars
        ):
            _close()

    _close()
    return drafts


def _page_range(
    start: int | None,
    end: int | None,
    page: int | None,
) -> tuple[int | None, int | None]:
    """Track the smallest and largest source page of a merged chunk."""
    if page is None:
        return start, end
    return (
        page if start is None else min(start, page),
        page if end is None else max(end, page),
    )


def _estimated_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _is_heading(block: dict) -> bool:
    block_type = str(block.get("type") or "").lower()
    if block_type not in HEADING_TYPES:
        return False
    try:
        level = int(block.get("text_level") or 1)
    except (TypeError, ValueError):
        level = 1
    return level <= MAX_TITLE_LEVEL


def _page_number(block: dict) -> int | None:
    page_idx = block.get("page_idx")
    if isinstance(page_idx, int):
        # MinerU page indexes are 0-based; humans and the PDF reader are 1-based.
        return page_idx + 1
    return None


def _block_text(block: dict) -> str | None:
    block_type = str(block.get("type") or "").lower()
    if block_type in {"text", "title", "heading"}:
        return _clean(block.get("text"))
    if block_type == "table":
        return _clean(block.get("table_body") or block.get("text"))
    if block_type in {"equation", "formula"}:
        latex = block.get("text") or block.get("latex")
        return _clean(latex)
    if block_type == "image":
        captions = block.get("img_caption") or []
        joined = " ".join(str(item) for item in captions)
        return _clean(joined) or None
    return _clean(block.get("text"))


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_oversized(text: str, *, max_chars: int) -> list[str]:
    """Split a single oversized block instead of dropping or truncating it."""
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(text):
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        while len(sentence) > max_chars:
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        current = sentence
    if current:
        pieces.append(current)
    return pieces
