"""Permission types for the project's explicit agent tool allowlist."""

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import cast

from agentscope.message import Base64Source, DataBlock, TextBlock
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import (
    Function,
    FunctionTool,
    ToolChunk,
    ToolMiddlewareBase,
)


class PaperReadTool(FunctionTool):
    def __init__(
        self,
        func: Function | Callable[..., Awaitable[dict[str, object]]],
        name: str | None = None,
        description: str | None = None,
        is_concurrency_safe: bool = True,
        is_read_only: bool = False,
        is_state_injected: bool = False,
        middlewares: list[ToolMiddlewareBase] | None = None,
    ) -> None:
        # AgentScope normalizes dict results in call(), but Function omits them.
        super().__init__(
            cast(Function, func),
            name=name,
            description=description,
            is_concurrency_safe=is_concurrency_safe,
            is_read_only=is_read_only,
            is_state_injected=is_state_injected,
            middlewares=middlewares,
        )

    async def check_permissions(self, *_args, **_kwargs) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Session-bound read tool allowed.",
        )


class PaperImageTool(PaperReadTool):
    """Return a figure as an image only when the current model can see one.

    A text-only model cannot use base64 data, and AgentScope would otherwise
    write the picture to a temporary file the agent has no tools to open. The
    caption and page are always returned.
    """

    supports_images: bool = False

    async def call(self, **kwargs) -> ToolChunk:
        result = self._func(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        image = result.pop("image_base64", None)
        media_type = result.pop("image_media_type", None)
        if not self.supports_images or not image or not media_type:
            result["note"] = (
                "The current model cannot view images, so only the caption "
                "and page are provided."
            )
            return ToolChunk(
                content=[TextBlock(text=json.dumps(result, ensure_ascii=False))]
            )
        return ToolChunk(
            content=[
                TextBlock(text=json.dumps(result, ensure_ascii=False)),
                DataBlock(source=Base64Source(data=image, media_type=media_type)),
            ]
        )


class UserReviewedWriteTool(FunctionTool):
    """Write tool that asks for approval unless the user opted out."""

    def __init__(
        self,
        *args,
        message: str,
        always_allow: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.message = message
        self.always_allow = always_allow

    async def check_permissions(self, *_args, **_kwargs) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW
            if self.always_allow
            else PermissionBehavior.ASK,
            message=self.message,
            bypass_immune=not self.always_allow,
        )


class ApprovedImportTool(UserReviewedWriteTool):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(
            *args,
            message="User review required before importing selected papers.",
            **kwargs,
        )


class ScheduleCreateTool(UserReviewedWriteTool):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(
            *args,
            message="User review required before creating a scheduled task.",
            **kwargs,
        )


class AskUserTool(FunctionTool):
    """Browser-executed question tool; the reply is an external tool result."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.is_external_tool = True

    async def check_permissions(self, *_args, **_kwargs) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Ask the current user in this session.",
        )
