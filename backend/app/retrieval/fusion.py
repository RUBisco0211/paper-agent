"""Reciprocal Rank Fusion over independent recall channels."""

from collections.abc import Iterable

from .domain import ChunkMatch, Evidence

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    *channels: Iterable[ChunkMatch],
    k: int = DEFAULT_RRF_K,
) -> list[Evidence]:
    """Fuse ranked channels without comparing incomparable raw scores."""
    merged: dict[str, Evidence] = {}
    for matches in channels:
        for match in matches:
            key = str(match.chunk.id)
            score = 1.0 / (k + match.rank)
            existing = merged.get(key)
            if existing is None:
                merged[key] = Evidence(
                    paper_id=match.chunk.paper_id,
                    chunk_ids=[match.chunk.id],
                    title_path=match.chunk.title_path,
                    snippet=match.chunk.content,
                    page_start=match.chunk.page_start,
                    page_end=match.chunk.page_end,
                    score=score,
                    chunk_index=match.chunk.chunk_index,
                    keyword_rank=match.rank if match.channel == "keyword" else None,
                    vector_rank=match.rank if match.channel == "vector" else None,
                )
                continue
            merged[key] = Evidence(
                paper_id=existing.paper_id,
                chunk_ids=existing.chunk_ids,
                title_path=existing.title_path,
                snippet=existing.snippet,
                page_start=existing.page_start,
                page_end=existing.page_end,
                score=existing.score + score,
                chunk_index=existing.chunk_index,
                keyword_rank=_first_rank(
                    existing.keyword_rank,
                    match.rank if match.channel == "keyword" else None,
                ),
                vector_rank=_first_rank(
                    existing.vector_rank,
                    match.rank if match.channel == "vector" else None,
                ),
            )
    return sorted(
        merged.values(),
        key=lambda item: (-item.score, str(item.chunk_ids[0])),
    )


def apply_budgets(
    evidence: list[Evidence],
    *,
    max_evidence: int,
    max_per_paper: int,
    merge_adjacent: bool = True,
    max_chars: int = 6000,
) -> list[Evidence]:
    """Keep the evidence set bounded, including a per-paper quota."""
    per_paper: dict[str, int] = {}
    selected: list[Evidence] = []
    for item in evidence:
        key = str(item.paper_id)
        if per_paper.get(key, 0) >= max_per_paper:
            continue
        per_paper[key] = per_paper.get(key, 0) + 1
        selected.append(item)
        if len(selected) >= max_evidence:
            break

    if not merge_adjacent:
        return selected
    return merge_adjacent_evidence(selected, max_chars=max_chars)


def merge_adjacent_evidence(
    evidence: list[Evidence],
    *,
    max_chars: int,
) -> list[Evidence]:
    """Merge consecutive chunks of one paper into a single evidence entry."""
    by_paper: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_paper.setdefault(str(item.paper_id), []).append(item)

    merged: list[Evidence] = []
    for items in by_paper.values():
        ordered = sorted(
            items,
            key=lambda item: (
                item.chunk_index if item.chunk_index is not None else -1,
            ),
        )
        current: Evidence | None = None
        for item in ordered:
            if current is None:
                current = item
                continue
            if _is_adjacent(current, item):
                current = current.merged_with(item, max_chars=max_chars)
                continue
            merged.append(current)
            current = item
        if current is not None:
            merged.append(current)

    return sorted(merged, key=lambda item: (-item.score, str(item.chunk_ids[0])))


def _is_adjacent(current: Evidence, candidate: Evidence) -> bool:
    if current.chunk_index is None or candidate.chunk_index is None:
        return False
    return candidate.chunk_index == current.chunk_index + len(current.chunk_ids)


def _first_rank(current: int | None, candidate: int | None) -> int | None:
    if current is not None:
        return current
    return candidate
