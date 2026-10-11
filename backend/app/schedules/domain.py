"""Scheduled task ownership and the bounded weekly cadence."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def weekly_cron(*, time: str, weekdays: list[str], timezone: str) -> str:
    """Convert a chosen local time and weekdays into AgentScope's cron form."""
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
        raise ValueError("执行时间须为 HH:MM")
    if not weekdays or len(weekdays) > 7 or len(set(weekdays)) != len(weekdays):
        raise ValueError("请选择一周内不重复的执行日")
    if any(day not in WEEKDAYS for day in weekdays):
        raise ValueError("执行日无效")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("任务时区无效") from exc
    hour, minute = time.split(":")
    selected = ",".join(day.upper() for day in WEEKDAYS if day in weekdays)
    return f"{int(minute)} {int(hour)} * * {selected}"
