"""Bound, weekly schedule creation through the business HTTP API."""

import re

import httpx

from .base import ScheduleCreateTool
from .request import business_request

_DAILY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_LOCAL_TIME = re.compile(
    r"^(?:(上午|早上|中午|下午|晚上)\s*)?"
    r"(\d{1,2})(?::(\d{1,2})|[点时](半|\d{1,2}分?)?)?$"
)


def normalize_schedule_time(value: str) -> str:
    """Normalize an explicit local clock time, never guess a vague period."""
    match = _LOCAL_TIME.fullmatch(value.strip())
    if match is None:
        raise ValueError("请给出明确的执行时间")
    period, hour_text, colon_minute, spoken_minute = match.groups()
    hour = int(hour_text)
    minute = (
        30
        if spoken_minute == "半"
        else int(colon_minute or (spoken_minute or "0").removesuffix("分"))
    )
    if period in {"下午", "晚上"} and 1 <= hour <= 11:
        hour += 12
    elif period in {"上午", "早上"} and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError("执行时间无效")
    return f"{hour:02d}:{minute:02d}"


def build_schedule_tool(
    user_id: str, agent_id: str, session_id: str, *, always_allow: bool = False
) -> ScheduleCreateTool:
    async def create_scheduled_task(
        name: str,
        prompt: str,
        time: str,
        weekdays: list[str] | None = None,
        notify_email: bool = False,
    ) -> dict:
        """Create a recurring task only when the user explicitly asks for one.

        Use the user's own prompt. Convert clear everyday clock expressions
        yourself: "中午12:30" -> "12:30", "下午3点" -> "15:00". Ask only if the
        exact clock time cannot be determined (for example "晚点"). Do not ask
        for a timezone: the system uses the user's saved local timezone.
        `weekdays` uses mon,tue,wed,thu,fri,sat,sun; omit it or use [] for every day.
        Translate explicit weekdays, workdays, or weekends yourself. The
        current session fixes the user and project scope. Set notify_email=True
        only when the user requests email notification of the result. The system
        sends only to the owner's verified email; never ask for a recipient.
        """
        try:
            return await business_request(
                "POST",
                "agent-schedules",
                json={
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "name": name,
                    "prompt": prompt,
                    "time": normalize_schedule_time(time),
                    "weekdays": weekdays or _DAILY,
                    "notify_email": notify_email,
                },
            )
        except httpx.HTTPError as exc:
            raise RuntimeError("定时任务创建失败，请稍后重试") from exc

    return ScheduleCreateTool(
        create_scheduled_task,
        is_read_only=False,
        is_concurrency_safe=False,
        always_allow=always_allow,
    )
