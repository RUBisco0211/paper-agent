"""Small, page-located index of MinerU's original content blocks."""

import math
import re
from html import unescape
from pathlib import PurePosixPath

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def build_block_index(content_list: list[dict]) -> dict:
    items: list[dict] = []
    types: list[str] = []
    for block_id, block in enumerate(content_list):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "other").lower()
        page_idx = block.get("page_idx")
        if not isinstance(page_idx, int) or page_idx < 0:
            continue
        text = _preview(block)
        formula = (
            _formula(block)
            if block_type in {"equation", "formula", "equation_interline"}
            else None
        )
        image_path = image_path_of(block)
        bbox = _rectangle(block.get("bbox"))
        page_size = _size(block.get("page_size"))
        coordinate_system = "page" if page_size else None
        if bbox and not page_size and bbox[2] <= 1000 and bbox[3] <= 1000:
            page_size = [1000.0, 1000.0]
            coordinate_system = "normalized"
        if bbox and page_size and (bbox[2] > page_size[0] or bbox[3] > page_size[1]):
            bbox = None
        if not page_size:
            bbox = None
        item = {
            "id": block_id,
            "type": block_type,
            "page": page_idx + 1,
            "text": text[:1200],
            "formula": formula,
            "image_path": image_path,
            "has_image": image_path is not None,
            "bbox": bbox,
            "page_size": page_size,
            "coordinate_system": coordinate_system,
        }
        items.append(item)
        if block_type not in types:
            types.append(block_type)
    return {"schema_version": 2, "types": types, "items": items}


def _preview(block: dict) -> str:
    raw = block.get("text") or block.get("table_body") or block.get("latex")
    if not raw and block.get("type") == "image":
        content = block.get("content")
        captions = block.get("img_caption") or (
            content.get("image_caption") if isinstance(content, dict) else []
        )
        raw = " ".join(str(value) for value in (captions or []))
    if not raw:
        return ""
    return _SPACE.sub(" ", unescape(_TAGS.sub(" ", str(raw)))).strip()


def block_full_text(block: dict) -> str:
    """Use the index's normalization without its preview length limit."""
    return _preview(block)


def _formula(block: dict) -> str | None:
    raw = block.get("latex") or block.get("text")
    if not raw and isinstance(block.get("content"), dict):
        raw = block["content"].get("math_content")
    return str(raw)[:4000] if isinstance(raw, str) and raw.strip() else None


def image_path_of(block: dict) -> str | None:
    """Return the block's image path when it points at a readable picture."""
    raw = block.get("img_path")
    if not raw and isinstance(block.get("content"), dict):
        source = block["content"].get("image_source")
        raw = source.get("path") if isinstance(source, dict) else None
    return normalize_image_path(raw)


def normalize_image_path(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    path = raw.removeprefix("./")
    parts = PurePosixPath(path).parts
    if (
        not parts
        or path.startswith("/")
        or ":" in path
        or ".." in parts
        or "\\" in path
    ):
        return None
    if PurePosixPath(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    return path


def _rectangle(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if not all(
        isinstance(number, (int, float)) and math.isfinite(number) for number in value
    ):
        return None
    x0, y0, x1, y1 = [float(number) for number in value]
    return [x0, y0, x1, y1] if 0 <= x0 < x1 and 0 <= y0 < y1 else None


def _size(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if not all(
        isinstance(number, (int, float)) and math.isfinite(number) and number > 0
        for number in value
    ):
        return None
    return [float(number) for number in value]
