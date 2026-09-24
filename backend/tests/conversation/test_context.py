from datetime import UTC, datetime
from uuid import uuid4

from app.conversation.context import last_user_message, project_messages
from app.sessions.domain import EntryType, SessionEntry


def _entry(entry_type: EntryType, payload: dict, sequence: int) -> SessionEntry:
    return SessionEntry(
        id=uuid4(),
        sequence=sequence,
        parent_id=None,
        type=entry_type,
        timestamp=datetime.now(UTC),
        payload=payload,
    )


def test_projection_keeps_only_user_and_assistant_messages() -> None:
    entries = [
        _entry(EntryType.MESSAGE, {"role": "user", "content": "hi"}, 1),
        _entry(EntryType.MODEL_CHANGE, {"provider": "openai", "model": "m"}, 2),
        _entry(EntryType.MESSAGE, {"role": "assistant", "content": "hello"}, 3),
        _entry(
            EntryType.MESSAGE,
            {"role": "assistant", "content": "tool plan", "trace": True},
            4,
        ),
        _entry(EntryType.MESSAGE, {"role": "system", "content": "ignored"}, 5),
        _entry(EntryType.MESSAGE, {"role": "user", "content": "   "}, 6),
    ]

    assert project_messages(entries) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_projection_truncates_tool_output_and_keeps_the_tail() -> None:
    entries = [
        _entry(
            EntryType.TOOL_RESULT,
            {"tool": "search_papers", "content": "x" * 5000},
            1,
        ),
        *[
            _entry(
                EntryType.MESSAGE, {"role": "user", "content": f"m{index}"}, index + 2
            )
            for index in range(5)
        ],
    ]

    projected = project_messages(entries, limit=3)

    assert [item["content"] for item in projected] == ["m2", "m3", "m4"]
    assert last_user_message(entries) == "m4"
    assert len(project_messages(entries)[0]["content"]) == 2000
