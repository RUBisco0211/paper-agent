from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.evidence.ranking import apply_budgets, reciprocal_rank_fusion
from app.retrieval.domain import Chunk, ChunkMatch


def _chunk(paper_id: UUID, index: int, content: str = "text") -> Chunk:
    return Chunk(
        id=uuid4(),
        paper_id=paper_id,
        chunk_index=index,
        title_path=f"Section {index}",
        content=content,
        page_start=index,
        page_end=index,
        block_ids=None,
        chunk_metadata=None,
        embedding_model=None,
        embedding_dimensions=None,
        created_at=datetime.now(UTC),
    )


def test_rrf_prefers_chunks_found_by_both_channels() -> None:
    paper_id = uuid4()
    shared = _chunk(paper_id, 0)
    keyword_only = _chunk(paper_id, 1)
    vector_only = _chunk(paper_id, 2)

    fused = reciprocal_rank_fusion(
        [
            ChunkMatch(shared, 0.9, 1, "keyword"),
            ChunkMatch(keyword_only, 0.5, 2, "keyword"),
        ],
        [
            ChunkMatch(vector_only, 0.8, 1, "vector"),
            ChunkMatch(shared, 0.7, 2, "vector"),
        ],
        k=60,
    )

    assert fused[0].chunk_ids == [shared.id]
    assert fused[0].keyword_rank == 1
    assert fused[0].vector_rank == 2
    assert fused[0].score > fused[1].score
    assert {item.chunk_ids[0] for item in fused[1:]} == {
        keyword_only.id,
        vector_only.id,
    }


def test_budgets_apply_per_paper_quota() -> None:
    first_paper, second_paper = uuid4(), uuid4()
    evidence = reciprocal_rank_fusion(
        [
            ChunkMatch(_chunk(first_paper, index), 1.0, index + 1, "keyword")
            for index in range(5)
        ],
        [
            ChunkMatch(_chunk(second_paper, 0), 1.0, 1, "keyword"),
        ],
    )

    selected = apply_budgets(
        evidence,
        max_evidence=10,
        max_per_paper=2,
        merge_adjacent=False,
    )

    assert len(selected) == 3
    assert sum(1 for item in selected if item.paper_id == first_paper) == 2
    assert sum(1 for item in selected if item.paper_id == second_paper) == 1


def test_budgets_merge_adjacent_chunks_of_one_paper() -> None:
    paper_id = uuid4()
    evidence = reciprocal_rank_fusion(
        [
            ChunkMatch(_chunk(paper_id, 0, "part one"), 1.0, 1, "keyword"),
            ChunkMatch(_chunk(paper_id, 1, "part two"), 1.0, 2, "keyword"),
            ChunkMatch(_chunk(paper_id, 5, "far away"), 1.0, 3, "keyword"),
        ],
    )

    merged = apply_budgets(
        evidence,
        max_evidence=10,
        max_per_paper=10,
        max_chars=10_000,
    )

    assert len(merged) == 2
    combined = next(item for item in merged if len(item.chunk_ids) == 2)
    assert combined.snippet == "part one\npart two"
    assert combined.page_start == 0
    assert combined.page_end == 1
