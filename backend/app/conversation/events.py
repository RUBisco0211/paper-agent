"""In-process event stream for session SSE subscribers.

Events carry a per-session monotonic sequence so a client can reconnect with a
cursor and replay what it missed. The MVP is a single process: the buffer lives
in memory and only promises short reconnect windows, not recovery across a
backend restart. Publishing is thread safe because a generation may run inside a
worker thread while subscribers sit on the event loop.
"""

import asyncio
import threading
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

EVENT_SCHEMA_VERSION = 1
POLL_INTERVAL_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class SessionEvent:
    event_id: str
    type: str
    resource_id: str
    sequence: int
    timestamp: datetime
    data: dict = field(default_factory=dict)
    schema_version: int = EVENT_SCHEMA_VERSION

    def to_payload(self) -> dict:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "resource_id": self.resource_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "schema_version": self.schema_version,
            "data": self.data,
        }


class _Channel:
    def __init__(self, buffer_size: int) -> None:
        self.events: deque[SessionEvent] = deque(maxlen=buffer_size)
        self.sequence = 0


class EventBroker:
    """Publishes and replays session events for SSE subscribers."""

    def __init__(self, *, buffer_size: int) -> None:
        self._buffer_size = buffer_size
        self._channels: dict[UUID, _Channel] = {}
        self._lock = threading.Lock()

    def publish(
        self, *, session_id: UUID, type: str, data: dict | None = None
    ) -> SessionEvent:
        with self._lock:
            channel = self._channels.get(session_id)
            if channel is None:
                channel = _Channel(self._buffer_size)
                self._channels[session_id] = channel
            channel.sequence += 1
            event = SessionEvent(
                event_id=str(channel.sequence),
                type=type,
                resource_id=str(session_id),
                sequence=channel.sequence,
                timestamp=datetime.now(UTC),
                data=data or {},
            )
            channel.events.append(event)
        logger.debug(
            "sessions.event.published",
            session_id=str(session_id),
            event_type=type,
            sequence=event.sequence,
        )
        return event

    def latest_sequence(self, session_id: UUID) -> int:
        with self._lock:
            channel = self._channels.get(session_id)
            return channel.sequence if channel else 0

    def replay(
        self, session_id: UUID, *, after_sequence: int = 0
    ) -> list[SessionEvent]:
        with self._lock:
            channel = self._channels.get(session_id)
            if channel is None:
                return []
            return [
                event for event in channel.events if event.sequence > after_sequence
            ]

    async def subscribe(
        self,
        session_id: UUID,
        *,
        after_sequence: int = 0,
        idle_timeout_seconds: float | None = None,
    ) -> AsyncIterator[SessionEvent | None]:
        """Yield events after the cursor; ``None`` marks an idle poll."""
        cursor = after_sequence
        idle = 0.0
        from ..platform.config import settings

        timeout = (
            settings.sse_idle_timeout_seconds
            if idle_timeout_seconds is None
            else idle_timeout_seconds
        )
        while True:
            pending = self.replay(session_id, after_sequence=cursor)
            if pending:
                idle = 0.0
                for event in pending:
                    cursor = event.sequence
                    yield event
                continue

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            idle += POLL_INTERVAL_SECONDS
            if timeout is not None and idle >= timeout:
                return
            yield None

    def clear(self, session_id: UUID) -> None:
        with self._lock:
            self._channels.pop(session_id, None)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sessions": len(self._channels),
                "buffered_events": sum(
                    len(channel.events) for channel in self._channels.values()
                ),
            }
