"""In-process task scheduling for background processing.

The MVP is a single process: ingestion and import jobs run as asyncio tasks on
the application event loop. The boundary exists so a Celery/Redis queue can
replace it without touching domain code, and so tests can execute work inline.
"""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Protocol

import structlog
from fastapi import Depends, Request

logger = structlog.get_logger(__name__)

TaskFactory = Callable[[], Awaitable[None]]


class TaskScheduler(Protocol):
    def submit(self, factory: TaskFactory, *, name: str) -> None: ...


class AsyncioTaskScheduler:
    """Run background work as tasks on the application event loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._flush_event: threading.Event | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def submit(self, factory: TaskFactory, *, name: str) -> None:
        if self._loop is None:
            raise RuntimeError("TaskScheduler 尚未绑定事件循环")
        future = asyncio.run_coroutine_threadsafe(factory(), self._loop)
        future.add_done_callback(lambda f: _log_task_result(f, name))
        logger.debug("task.submitted", task_name=name)

    async def shutdown(self) -> None:
        # Tasks are fire-and-forget; nothing to join beyond letting the loop
        # finish the currently scheduled callbacks.
        await asyncio.sleep(0)


class InlineTaskScheduler:
    """Execute background work before the request returns; used by tests."""

    def submit(self, factory: TaskFactory, *, name: str) -> None:
        logger.debug("task.inline", task_name=name)
        asyncio.run(factory())


def _log_task_result(future: Any, name: str) -> None:
    try:
        future.result()
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.error(
            "task.failed",
            task_name=name,
            error_type=type(exc).__name__,
        )
    else:
        logger.debug("task.completed", task_name=name)


def get_task_scheduler(request: Request) -> TaskScheduler:
    scheduler = getattr(request.app.state, "task_scheduler", None)
    if scheduler is None:
        raise RuntimeError("TaskScheduler 未初始化")
    return scheduler


TaskSchedulerDep = Annotated[TaskScheduler, Depends(get_task_scheduler)]
