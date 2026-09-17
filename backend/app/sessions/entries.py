"""Append-only entry log for one session.

Entries live as JSONL in object storage: the first line is the session header,
every following line is one immutable entry. ``parent_id`` links entries so the
context of a session can be rebuilt from its leaf, and sequence numbers let a
client reconnect without replaying everything.
"""

import json
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import UUID, uuid4

import structlog

from ..platform.storage import ObjectStorage, session_entries_key
from .domain import EntryType, MessageRole, SessionContext, SessionEntry

logger = structlog.get_logger(__name__)

ENTRY_SCHEMA_VERSION = 1
DEFAULT_ENTRY_LIMIT = 200
MAX_ENTRY_LIMIT = 500


class EntryStore:
    """Reads and appends the JSONL entry log of a session."""

    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    # Reads -----------------------------------------------------------------
    def list_entries(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        after_sequence: int = 0,
        limit: int = DEFAULT_ENTRY_LIMIT,
    ) -> list[SessionEntry]:
        entries = [
            entry
            for entry in self._read(user_id=user_id, session_id=session_id)
            if entry.sequence > after_sequence
        ]
        return entries[: min(limit, MAX_ENTRY_LIMIT)]

    def last_entry(self, *, user_id: UUID, session_id: UUID) -> SessionEntry | None:
        entries = self._read(user_id=user_id, session_id=session_id)
        return entries[-1] if entries else None

    def count_entries(self, *, user_id: UUID, session_id: UUID) -> int:
        return len(self._read(user_id=user_id, session_id=session_id))

    def session_context(self, *, user_id: UUID, session_id: UUID) -> SessionContext:
        """本会话的讨论范围。

        范围不落数据库，而是会话自己在创建时写入的一条 ``session_context`` Entry：
        它排在日志最前面，所以这里只需要读到第一条匹配即可。
        """
        key = session_entries_key(str(user_id), str(session_id))
        if not self._storage.exists(key):
            return SessionContext()
        for entry in _iter_entries(self._storage.open(key)):
            if entry.type is EntryType.SESSION_CONTEXT:
                return SessionContext(
                    kind=str(entry.payload.get("kind") or "library"),
                    project_id=_uuid_or_none(entry.payload.get("project_id")),
                    paper_id=_uuid_or_none(entry.payload.get("paper_id")),
                    paper_title=entry.payload.get("paper_title"),
                )
        return SessionContext()

    def write_session_context(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        context: SessionContext,
    ) -> SessionEntry:
        return self.append(
            user_id=user_id,
            session_id=session_id,
            entry_type=EntryType.SESSION_CONTEXT,
            payload={
                "kind": context.kind,
                "project_id": str(context.project_id) if context.project_id else None,
                "paper_id": str(context.paper_id) if context.paper_id else None,
                "paper_title": context.paper_title,
            },
        )

    # Writes ----------------------------------------------------------------
    def append(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        entry_type: EntryType,
        payload: dict,
        parent_id: UUID | None = None,
        timestamp: datetime | None = None,
    ) -> SessionEntry:
        existing = self._read(user_id=user_id, session_id=session_id)
        parent = (
            parent_id
            if parent_id is not None
            else (existing[-1].id if existing else None)
        )
        entry = SessionEntry(
            id=uuid4(),
            sequence=(existing[-1].sequence + 1) if existing else 1,
            parent_id=parent,
            type=entry_type,
            timestamp=timestamp or datetime.now(UTC),
            payload=payload,
            schema_version=ENTRY_SCHEMA_VERSION,
        )
        line = json.dumps(entry.to_json(), ensure_ascii=False) + "\n"
        key = session_entries_key(str(user_id), str(session_id))
        self._storage.append_bytes(key, line.encode("utf-8"))
        logger.debug(
            "sessions.entry.appended",
            session_id=str(session_id),
            entry_id=str(entry.id),
            entry_type=entry.type.value,
            sequence=entry.sequence,
        )
        return entry

    def append_message(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        role: MessageRole,
        content: str,
        **extra: object,
    ) -> SessionEntry:
        return self.append(
            user_id=user_id,
            session_id=session_id,
            entry_type=EntryType.MESSAGE,
            payload={"role": role.value, "content": content, **extra},
        )

    def purge(self, *, user_id: UUID, session_id: UUID) -> bool:
        key = session_entries_key(str(user_id), str(session_id))
        existed = self._storage.exists(key)
        self._storage.delete(key)
        return existed

    # Internals -------------------------------------------------------------
    def _read(self, *, user_id: UUID, session_id: UUID) -> list[SessionEntry]:
        key = session_entries_key(str(user_id), str(session_id))
        if not self._storage.exists(key):
            return []
        return list(_iter_entries(self._storage.open(key)))


def _uuid_or_none(value: object) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _iter_entries(stream: BinaryIO):
    for raw_line in stream:
        line = raw_line.decode("utf-8").strip()
        if not line:
            continue
        try:
            yield SessionEntry.from_json(json.loads(line))
        except (ValueError, KeyError, TypeError):
            # A corrupt tail must not make the whole history unreadable.
            logger.warning("sessions.entry.skipped_corrupt_line")
            continue
