"""Render one PDF page of MinerU blocks as Markdown for the agent reader.

MinerU Markdown is a continuous document without page boundaries; the original
PDF page lives on each block's ``page_idx``. Reading by page therefore renders
the blocks of one page instead of slicing the Markdown string.
"""

from .blocks import block_full_text, image_path_of

IMAGE_TYPES = frozenset({"image", "chart"})
FORMULA_TYPES = frozenset({"equation", "formula", "equation_interline"})
TABLE_TYPES = frozenset({"table"})

TRUNCATED_NOTE = "\n\n[本页其余内容超出单次读取上限，未返回]"


def count_pages(content_list: list[dict]) -> int:
    """Return the number of PDF pages the parsed blocks cover."""
    pages = [
        block["page_idx"]
        for block in content_list
        if isinstance(block, dict) and isinstance(block.get("page_idx"), int)
        and block["page_idx"] >= 0
    ]
    return max(pages) + 1 if pages else 0


def build_page(
    content_list: list[dict],
    page: int,
    *,
    max_chars: int = 12000,
    unreadable_image_ids: frozenset[int] = frozenset(),
) -> dict:
    """Render one 1-based PDF page, plus the pictures it can actually serve.

    ``unreadable_image_ids`` are blocks that have a picture but cannot be
    served (for example because the file is too large); they keep their caption
    and lose the read marker, so the reader never points at a dead image.
    """
    blocks = [
        (block_id, block)
        for block_id, block in enumerate(content_list)
        if isinstance(block, dict) and block.get("page_idx") == page - 1
    ]
    parts: list[str] = []
    images: list[dict] = []
    omitted: list[int] = []
    partial: int | None = None
    used = 0
    truncated = False

    for block_id, block in blocks:
        kind = str(block.get("type") or "other").lower()
        readable = (
            kind in IMAGE_TYPES
            and image_path_of(block) is not None
            and block_id not in unreadable_image_ids
        )
        piece = _render(block_id, block, kind, page, readable=readable)
        if kind in IMAGE_TYPES and readable:
            images.append({"block_id": block_id, "caption": _caption(block) or None})
        if not piece:
            continue
        if used + len(piece) <= max_chars:
            parts.append(piece)
            used += len(piece)
            continue
        truncated = True
        if not parts:
            parts.append(piece[:max_chars] + "…")
            used = max_chars
            partial = block_id
        else:
            omitted.append(block_id)

    markdown = "\n\n".join(parts)
    if truncated:
        markdown += TRUNCATED_NOTE
    return {
        "page": page,
        "total_pages": count_pages(content_list),
        "markdown": markdown,
        "images": images,
        "truncated": truncated,
        "partial_block_id": partial,
        "omitted_block_ids": omitted,
    }


def _render(block_id: int, block: dict, kind: str, page: int, *, readable: bool) -> str:
    if kind in IMAGE_TYPES:
        caption = _caption(block)
        if not readable:
            return f"[图片] {caption}" if caption else ""
        marker = f"[图片 | block {block_id} | 第{page}页]"
        return f"{marker} 图注：{caption}" if caption else marker
    if kind in FORMULA_TYPES:
        latex = _latex(block)
        return f"$$\n{latex}\n$$" if latex else ""
    if kind in TABLE_TYPES:
        caption = _caption(block)
        body = str(block.get("table_body") or block.get("text") or "").strip()
        return "\n".join(item for item in (caption, body) if item)
    return block_full_text(block)


def _caption(block: dict) -> str:
    raw = block.get("img_caption") or block.get("table_caption")
    content = block.get("content")
    if not raw and isinstance(content, dict):
        raw = content.get("image_caption") or content.get("table_caption")
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [str(value) for value in raw]
    else:
        values = []
    return " ".join(value.strip() for value in values if value.strip())


def _latex(block: dict) -> str:
    raw = block.get("latex") or block.get("text")
    content = block.get("content")
    if not raw and isinstance(content, dict):
        raw = content.get("math_content")
    return str(raw).strip() if isinstance(raw, str) and raw.strip() else ""
