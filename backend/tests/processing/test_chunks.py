from app.literature_support.processing.chunks import build_chunks


def _block(block_type: str, text: str, page: int = 0, **extra) -> dict:
    return {"type": block_type, "text": text, "page_idx": page, **extra}


def test_headings_build_a_title_path_and_pages_are_one_based() -> None:
    chunks = build_chunks(
        [
            _block("title", "3 Method", page=2, text_level=1),
            _block("title", "3.1 Attention", page=2, text_level=2),
            _block("text", "We use scaled dot product attention.", page=2),
        ],
    )

    assert len(chunks) == 1
    assert chunks[0].title_path == "3 Method > 3.1 Attention"
    assert chunks[0].page_start == 3
    assert chunks[0].page_end == 3
    assert chunks[0].block_ids == [0, 1, 2]
    assert "scaled dot product attention" in chunks[0].content


def test_chunks_close_on_the_token_budget() -> None:
    paragraph = " ".join(["token"] * 300)
    chunks = build_chunks(
        [_block("text", paragraph, page=index) for index in range(4)],
        target_tokens=100,
        max_chars=10_000,
    )

    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.page_start is not None for chunk in chunks)


def test_non_text_blocks_are_mapped_to_searchable_text() -> None:
    chunks = build_chunks(
        [
            _block("table", "", table_body="<table><tr><td>BLEU</td></tr></table>"),
            _block("equation", "E = mc^2"),
            {"type": "image", "img_caption": ["Figure 1: Architecture"], "page_idx": 1},
            _block("text", "Body text."),
        ],
        target_tokens=10_000,
    )

    content = chunks[0].content
    assert "BLEU" in content
    assert "E = mc^2" in content
    assert "Figure 1: Architecture" in content
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2


def test_display_formula_block_keeps_its_latex_when_text_is_empty() -> None:
    chunks = build_chunks(
        [
            _block("text", "The objective is"),
            {"type": "equation_interline", "text": "", "latex": "$$L = -\\log p$$", "page_idx": 0},
            _block("text", "under the softmax."),
        ],
        target_tokens=10_000,
    )

    assert len(chunks) == 1
    assert "$$L = -\\log p$$" in chunks[0].content


def test_figure_placeholder_carries_page_section_and_caption() -> None:
    chunks = build_chunks(
        [
            _block("title", "4 Experiments", page=2, text_level=1),
            _block("title", "4.2 Ablation", page=2, text_level=2),
            {
                "type": "image",
                "img_caption": ["Figure 3: Perplexity across models"],
                "page_idx": 2,
            },
        ],
        target_tokens=10_000,
    )

    assert (
        "[图 第3页 | 4 Experiments > 4.2 Ablation] Figure 3: Perplexity across models"
        in chunks[0].content
    )


def test_captionless_figure_still_reaches_the_chunk_body() -> None:
    chunks = build_chunks(
        [
            _block("title", "5 Results", page=6, text_level=1),
            {"type": "image", "page_idx": 6},
            _block("text", "The trend is consistent.", page=6),
        ],
        target_tokens=10_000,
    )

    assert "[图 第7页 | 5 Results]" in chunks[0].content


def test_figure_before_any_heading_keeps_only_its_page() -> None:
    chunks = build_chunks(
        [{"type": "image", "page_idx": 0}, _block("text", "Front matter.", page=0)],
        target_tokens=10_000,
    )

    assert "[图 第1页]" in chunks[0].content


def test_figure_metadata_lists_page_section_caption_and_path() -> None:
    chunks = build_chunks(
        [
            _block("title", "4 Experiments", page=2, text_level=1),
            {
                "type": "image",
                "img_caption": ["Figure 3: Perplexity across models"],
                "img_path": "images/fig3.png",
                "page_idx": 2,
            },
        ],
        target_tokens=10_000,
    )

    figures = chunks[0].chunk_metadata["figures"]
    assert figures == [
        {
            "page": 3,
            "section": "4 Experiments",
            "caption": "Figure 3: Perplexity across models",
            "path": "images/fig3.png",
        }
    ]
    assert "images/fig3.png" not in chunks[0].content


def test_figure_metadata_survives_an_oversized_split() -> None:
    filler = " ".join(["sentence"] * 200)
    chunks = build_chunks(
        [
            _block("text", filler, page=0),
            {"type": "image", "img_path": "images/fig9.png", "page_idx": 1},
        ],
        target_tokens=10_000,
        max_chars=300,
    )

    pages = {
        figure["page"]
        for chunk in chunks
        for figure in chunk.chunk_metadata.get("figures", [])
    }
    assert pages == {2}
    assert sum(
        1
        for chunk in chunks
        for _ in chunk.chunk_metadata.get("figures", [])
    ) == 1


def test_oversized_block_is_split_instead_of_truncated() -> None:
    long_text = " ".join(["sentence"] * 400)

    chunks = build_chunks(
        [_block("text", long_text)],
        target_tokens=10_000,
        max_chars=200,
    )

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 200 for chunk in chunks)
    assert sum(len(chunk.content) for chunk in chunks) >= len(long_text) * 0.95
    assert all(chunk.chunk_metadata["source_ranges"] for chunk in chunks)


def test_split_chunk_keeps_exact_source_offsets_and_its_own_page() -> None:
    blocks = [
        _block("text", "alpha " * 45, page=0, bbox=[1, 2, 3, 4]),
        _block("text", "beta " * 45, page=1),
    ]
    chunks = build_chunks(blocks, target_tokens=10_000, max_chars=80)

    assert {chunk.page_start for chunk in chunks} == {1, 2}
    for chunk in chunks:
        rebuilt = "".join(
            blocks[source["block_id"]]["text"][source["char_start"]:source["char_end"]]
            for source in chunk.chunk_metadata["source_ranges"]
        )
        assert rebuilt.replace(" ", "") == chunk.content.replace(" ", "")


def test_empty_blocks_produce_no_chunks() -> None:
    assert build_chunks([]) == []
    assert build_chunks([{"type": "image"}]) == []


def test_nested_display_formula_reads_math_content_when_flat_fields_are_absent() -> None:
    chunks = build_chunks(
        [
            _block("text", "The objective is"),
            {
                "type": "equation_interline",
                "page_idx": 0,
                "content": {"math_content": "$$L = -\\log p$$"},
            },
        ],
        target_tokens=10_000,
    )

    assert len(chunks) == 1
    assert "$$L = -\\log p$$" in chunks[0].content


def test_nested_figure_caption_reads_image_caption_when_flat_field_is_absent() -> None:
    chunks = build_chunks(
        [
            _block("title", "3 Method", page=0, text_level=1),
            {
                "type": "image",
                "page_idx": 0,
                "content": {"image_caption": ["Figure 1: Architecture"]},
            },
        ],
        target_tokens=10_000,
    )

    assert "[图 第1页 | 3 Method] Figure 1: Architecture" in chunks[0].content
    assert chunks[0].chunk_metadata["figures"][0]["caption"] == (
        "Figure 1: Architecture"
    )
