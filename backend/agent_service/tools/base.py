"""Permission types for the project's explicit agent tool allowlist."""

from collections.abc import Awaitable, Callable
from typing import cast

from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import Function, FunctionTool, ToolMiddlewareBase


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
