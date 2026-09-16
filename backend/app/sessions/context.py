"""Projection of the entry log into model messages.

Context is rebuilt along the entry chain instead of being stored twice, so a
compaction entry or a model change never has to rewrite history.
"""

from .domain import EntryType, MessageRole, SessionEntry

DEFAULT_CONTEXT_ENTRIES = 40
TOOL_CONTENT_MAX_CHARS = 2000


def project_messages(
    entries: list[SessionEntry],
    *,
    limit: int = DEFAULT_CONTEXT_ENTRIES,
) -> list[dict]:
    """Turn entries into chat messages, newest tail wins."""
    messages: list[dict] = []
    for entry in entries[-limit:]:
        if entry.type is EntryType.MESSAGE:
            role = str(entry.payload.get("role", ""))
            content = str(entry.payload.get("content", "")).strip()
            if role not in {MessageRole.USER.value, MessageRole.ASSISTANT.value}:
                continue
            if not content:
                continue
            messages.append({"role": role, "content": content})
        elif entry.type is EntryType.TOOL_RESULT:
            tool_content = str(entry.payload.get("content", ""))[
                :TOOL_CONTENT_MAX_CHARS
            ]
            messages.append(
                {
                    "role": "tool",
                    "name": str(entry.payload.get("tool", "tool")),
                    "content": tool_content,
                },
            )
    return messages


def last_user_message(entries: list[SessionEntry]) -> str | None:
    for entry in reversed(entries):
        if (
            entry.type is EntryType.MESSAGE
            and entry.payload.get("role") == MessageRole.USER.value
        ):
            return str(entry.payload.get("content") or "")
    return None
