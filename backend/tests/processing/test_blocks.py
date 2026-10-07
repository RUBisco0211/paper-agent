from app.processing.blocks import build_block_index


def test_block_index_retains_mineru_types_and_reliable_page_geometry() -> None:
    index = build_block_index(
        [
            {
                "type": "title",
                "text": "Introduction",
                "page_idx": 0,
                "bbox": [10, 20, 200, 50],
                "page_size": [612, 792],
            },
            {
                "type": "table",
                "table_body": "<table><tr><td>Accuracy</td></tr></table>",
                "page_idx": 1,
                "bbox": [10, 20, 700, 100],
                "page_size": [612, 792],
            },
            {"type": "image", "page_idx": 1},
            {
                "type": "text",
                "text": "Normalized",
                "page_idx": 2,
                "bbox": [100, 200, 500, 300],
            },
        ]
    )

    assert index["types"] == ["title", "table", "image", "text"]
    assert index["items"][0]["page"] == 1
    assert index["items"][0]["bbox"] == [10, 20, 200, 50]
    assert index["items"][1]["text"] == "Accuracy"
    assert index["items"][1]["bbox"] is None
    assert index["items"][2]["text"] == ""
    assert index["items"][3]["bbox"] == [100, 200, 500, 300]
    assert index["items"][3]["coordinate_system"] == "normalized"


def test_block_index_keeps_image_and_equation_preview_sources() -> None:
    index = build_block_index(
        [
            {
                "type": "image",
                "page_idx": 0,
                "img_path": "images/figure-1.png",
                "img_caption": ["Figure 1"],
            },
            {
                "type": "equation",
                "page_idx": 0,
                "text": r"E = mc^2",
                "text_format": "latex",
            },
            {"type": "equation", "page_idx": 1, "img_path": "images/equation-1.png"},
        ]
    )

    assert index["items"][0]["image_path"] == "images/figure-1.png"
    assert index["items"][0]["text"] == "Figure 1"
    assert index["items"][1]["formula"] == r"E = mc^2"
    assert index["items"][2]["image_path"] == "images/equation-1.png"


def test_block_index_rejects_paths_outside_the_parsed_artifact() -> None:
    index = build_block_index(
        [
            {"type": "image", "page_idx": 0, "img_path": "../private.png"},
            {"type": "image", "page_idx": 0, "img_path": "https://example.com/a.png"},
        ]
    )
    assert all(item["has_image"] is False for item in index["items"])
