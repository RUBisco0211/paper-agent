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
