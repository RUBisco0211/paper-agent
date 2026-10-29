import pytest
from agentscope.message import AssistantMsg, TextBlock
from pydantic import ValidationError

from agent_service.quoted_chat import (
    MessageQuote,
    PaperQuote,
    QuotedChatRequest,
    apply_mentions,
    image_model_unavailable,
    render_quoted_content,
    validate_message_quote,
)


@pytest.mark.asyncio
async def test_message_quote_accepts_rendered_selection_when_source_is_completed():
    source = AssistantMsg("assistant", [TextBlock(text="A verified finding")])
    source.finished_at = source.created_at
    quote = MessageQuote(
        source_message_id=source.id,
        block_index=0,
        start=0,
        end=8,
        selected_text="Invented",
        comment="Check this",
    )
    validate_message_quote(source, quote)


def test_message_quote_rejects_missing_or_non_text_source_block():
    source = AssistantMsg("assistant", [TextBlock(text="A verified finding")])
    source.finished_at = source.created_at
    quote = MessageQuote(source_message_id=source.id, block_index=1,
                         start=0, end=8, selected_text="Invented", comment="Check this")
    with pytest.raises(ValueError, match="selection_mismatch"):
        validate_message_quote(source, quote)


def test_quoted_content_bounds_source_text_and_keeps_comment():
    quote = MessageQuote(
        source_message_id="source",
        block_index=0,
        start=0,
        end=5,
        selected_text="claim",
        comment="Is this supported?",
    )
    content = render_quoted_content("Please investigate", [quote])
    assert "claim" in content and "Is this supported?" in content
    assert "source" not in content


def test_quoted_chat_accepts_an_empty_comment_and_binds_eight_references():
    reference = MessageQuote(
        source_message_id="source", block_index=0, start=0, end=5,
        selected_text="claim", comment="",
    )
    body = QuotedChatRequest(
        agent_id="agent", session_id="session", references=[reference] * 8
    )
    assert len(body.references) == 8
    assert "评论：" not in render_quoted_content("", body.references)
    with pytest.raises(ValidationError):
        QuotedChatRequest(
            agent_id="agent", session_id="session", references=[reference] * 9
        )


def test_image_quote_allows_captionless_block_with_empty_comment():
    quote = PaperQuote(
        kind="parsed_block", user_paper_id="paper", version="v1", page=2,
        block_id=4, start=0, end=0, selected_text="", comment="", include_image=True,
    )
    assert "图片或图表" in render_quoted_content("", [quote])


def test_image_quote_rejects_a_provider_that_discards_image_blocks():
    assert image_model_unavailable("deepseek_credential")
    assert not image_model_unavailable("openai_credential")


def test_pdf_quote_preserves_many_rectangles_only_in_metadata():
    rects = [[0.1, index / 100, 0.2, index / 100 + 0.005] for index in range(30)]
    quote = PaperQuote(kind="pdf_selection", user_paper_id="paper", version="v1",
                       page=2, rects=rects, selected_text="selected", comment="")
    body = QuotedChatRequest(agent_id="agent", session_id="session", references=[quote])
    assert quote.rects == rects
    content = render_quoted_content("review", body.references)
    assert "selected" in content
    assert "rects" not in content
    assert "0.005" not in content


def test_pdf_quote_shows_only_paper_and_page_as_source():
    quote = PaperQuote(
        kind="pdf_selection",
        user_paper_id="paper",
        version="v1",
        page=2,
        selected_text="Abstract",
        comment="",
        source_title="Example",
    )
    content = render_quoted_content("翻译", [quote])
    assert "来源：文献《Example》第 2 页" in content
    assert "PDF 选区" not in content
    assert "未核对" not in content


def test_mentioned_paper_becomes_a_title_and_id_inside_the_sentence():
    text = "对比 @{{1}} 和 @{{2}} 的安全性做法"
    rendered = apply_mentions(
        text,
        {
            1: {
                "title": "Safe and Scalable Multi-Drone Payload Transport",
                "has_fulltext": True,
                "user_paper_id": "11111111-1111-1111-1111-111111111111",
            },
            2: {
                "title": "Beyond Safety Filtering",
                "has_fulltext": False,
                "user_paper_id": "22222222-2222-2222-2222-222222222222",
            },
        },
    )

    assert (
        "@《Safe and Scalable Multi-Drone Payload Transport》"
        "(paper:11111111-1111-1111-1111-111111111111)"
    ) in rendered
    assert "@《Beyond Safety Filtering》(paper:22222222-2222-2222-2222-222222222222)（待补全文）" in rendered
    assert "@{{" not in rendered


def test_quoted_content_omits_the_source_header_when_only_papers_are_mentioned():
    assert render_quoted_content("只问一句", []) == "只问一句"
