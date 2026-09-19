"""Projection of the entry log into model messages.

Context is rebuilt along the entry chain instead of being stored twice, so a
compaction entry or a model change never has to rewrite history.
"""

from .domain import EntryType, MessageRole, SessionContext, SessionEntry

DEFAULT_CONTEXT_ENTRIES = 40
TOOL_CONTENT_MAX_CHARS = 2000


SCOPE_PROMPTS: dict[str, str] = {
    "paper": (
        "本次会话只讨论这一篇文献：{title}。它属于用户文献库中的单篇文献范围，"
        "检索与引用都不得超出该文献。"
    ),
    "project": (
        "本次会话只讨论用户所选项目中的文献（项目由后端绑定，不能用参数扩大范围）。"
    ),
    "library": ("本次会话可以使用用户文献库中的全部文献；需要列举时使用文献列表工具。"),
}


def scope_system_message(context: SessionContext) -> str:
    """会话范围以系统提示词的形式注入，而不是靠模型自己记住。"""
    template = SCOPE_PROMPTS.get(context.kind, SCOPE_PROMPTS["library"])
    return template.format(title=context.paper_title or "（未命名文献）")


def project_messages(
    entries: list[SessionEntry],
    *,
    context: SessionContext | None = None,
    limit: int = DEFAULT_CONTEXT_ENTRIES,
) -> list[dict]:
    """Turn entries into chat messages, newest tail wins.

    会话范围作为第一条 system 消息注入；``session_context`` Entry 只是范围的历史记录，
    不作为对话内容参与投影。
    """
    messages: list[dict] = []
    if context is not None:
        messages.append({"role": "system", "content": scope_system_message(context)})
    for entry in entries[-limit:]:
        if entry.type is EntryType.SESSION_CONTEXT:
            continue
        if entry.type is EntryType.MESSAGE:
            if entry.payload.get("trace") is True:
                continue
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
