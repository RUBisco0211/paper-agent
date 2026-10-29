"""One PDF page of MinerU blocks is rendered as Markdown for the agent reader."""

from app.literature_support.importing.pages import build_page


def _text(page, text):
    return {"type": "text", "page_idx": page, "text": text}


def _image(page, path, caption):
    return {
        "type": "image",
        "page_idx": page,
        "img_path": path,
        "img_caption": [caption],
    }


def test_page_markdown_keeps_only_the_requested_pdf_page():
    content = [_text(0, "第一页正文"), _text(1, "第二页正文"), _text(2, "第三页正文")]

    page = build_page(content, 2)

    assert "第二页正文" in page["markdown"]
    assert "第一页正文" not in page["markdown"]
    assert "第三页正文" not in page["markdown"]
    assert page["page"] == 2
    assert page["total_pages"] == 3


def test_page_markdown_names_every_image_block_on_the_page():
    content = [
        _text(0, "见下图"),
        _image(0, "images/plot.png", "图 1：准确率对比"),
        _image(0, "images/other.png", "图 2：消融结果"),
    ]

    page = build_page(content, 1)

    assert [item["block_id"] for item in page["images"]] == [1, 2]
    assert page["images"][0]["caption"] == "图 1：准确率对比"
    assert "[图片 | block 1 | 第1页]" in page["markdown"]
    assert "images/plot.png" not in page["markdown"]


def test_page_markdown_keeps_equations_as_latex():
    content = [
        {
            "type": "equation",
            "page_idx": 0,
            "latex": r"E = mc^2",
        }
    ]

    page = build_page(content, 1)

    assert "$$" in page["markdown"]
    assert "E = mc^2" in page["markdown"]


def test_page_markdown_marks_the_rest_when_a_page_exceeds_the_budget():
    content = [_text(0, "甲" * 400), _text(0, "乙" * 400)]

    page = build_page(content, 1, max_chars=500)

    assert page["truncated"] is True
    assert page["omitted_block_ids"] == [1]
    assert page["partial_block_id"] is None
    assert "其余" in page["markdown"]
    assert "乙" not in page["markdown"]


def test_page_markdown_reports_a_block_that_is_only_partly_returned():
    content = [_text(0, "甲" * 900)]

    page = build_page(content, 1, max_chars=500)

    assert page["truncated"] is True
    assert page["partial_block_id"] == 0
    assert page["omitted_block_ids"] == []


def test_page_markdown_hides_a_picture_marker_when_the_block_has_no_source():
    content = [{"type": "image", "page_idx": 0, "img_caption": ["图 1"]}]

    page = build_page(content, 1)

    assert page["images"] == []
    assert "block 0" not in page["markdown"]
    assert "图 1" in page["markdown"]


def test_page_markdown_hides_a_picture_marker_when_the_image_cannot_be_served():
    content = [_image(0, "images/huge.png", "图 1")]

    page = build_page(content, 1, unreadable_image_ids=frozenset({0}))

    assert page["images"] == []
    assert "block 0" not in page["markdown"]
    assert "图 1" in page["markdown"]


def test_page_markdown_returns_an_empty_page_when_nothing_was_parsed():
    page = build_page([_text(0, "只有一页")], 5)

    assert page["markdown"] == ""
    assert page["images"] == []
    assert page["truncated"] is False
    assert page["total_pages"] == 1
