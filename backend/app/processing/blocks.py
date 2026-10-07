"""Small, page-located index of MinerU's original content blocks."""

import math
import re
from html import unescape

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
            "bbox": bbox,
            "page_size": page_size,
            "coordinate_system": coordinate_system,
        }
        items.append(item)
        if block_type not in types:
            types.append(block_type)
    return {"types": types, "items": items}


def _preview(block: dict) -> str:
    raw = block.get("text") or block.get("table_body") or block.get("latex")
    if not raw and block.get("type") == "image":
        raw = " ".join(str(value) for value in block.get("img_caption") or [])
    if not raw:
        return ""
    return _SPACE.sub(" ", unescape(_TAGS.sub(" ", str(raw)))).strip()


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
