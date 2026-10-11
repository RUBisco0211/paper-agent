"""Browser-executed clarification tool."""

from .base import AskUserTool


def build_question_tool() -> AskUserTool:
    async def ask_user(questions: list[dict]) -> dict:
        """Ask up to three concise questions when an answer is needed to continue.

        Each question has a unique `name`, a `prompt`, a `type` of `single`,
        `multiple`, or `text`, optional `description`, `required` (default
        true), and for choice types an `options` list of `{value, label}`.
        Choice questions can also set `allow_other` to accept free text.
        Do not use this to request authorization for another tool. The
        browser executes this tool.
        """
        raise RuntimeError("ask_user is executed by the browser")

    return AskUserTool(ask_user, is_read_only=False, is_concurrency_safe=False)
