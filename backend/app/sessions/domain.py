"""Session domain: conversation boundary, entries and pending input."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

TITLE_MAX_LENGTH = 200
MESSAGE_MAX_LENGTH = 8000


class Delivery(StrEnum):
    """How a pending user message should be handed to the running agent."""

    STEERING = "steering"
    FOLLOW_UP = "follow_up"


class EntryType(StrEnum):
    MESSAGE = "message"
    TOOL_RESULT = "tool_result"
    MODEL_CHANGE = "model_change"
    CONTEXT_COMPACTION = "context_compaction"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class GenerationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class StopReason(StrEnum):
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Session:
    id: UUID
    user_id: UUID
    project_id: UUID | None
    title: str | None
    created_at: datetime
    updated_at: datetime
    #: Set when the session is about exactly one library entry. API value
    #: ``paper``; the interface calls this scope "单篇文献".
    user_paper_id: UUID | None = None

    @property
    def scope(self) -> str:
        """``project`` | ``paper`` | ``library`` (界面「全局」)."""
        if self.project_id is not None:
            return "project"
        if self.user_paper_id is not None:
            return "paper"
        return "library"


@dataclass(frozen=True, slots=True)
class PendingMessage:
    id: UUID
    session_id: UUID
    delivery: Delivery
    position: int
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Citation:
    """Evidence a stored answer is allowed to point at."""

    citation_id: str
    session_id: UUID
    user_paper_id: UUID
    chunk_ids: list[UUID] = field(default_factory=list)
    title_path: str | None = None
    snippet: str = ""
    page_start: int | None = None
    page_end: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SessionEntry:
    """One immutable node of a session's append-only log."""

    id: UUID
    sequence: int
    parent_id: UUID | None
    type: EntryType
    timestamp: datetime
    payload: dict
    schema_version: int = 1

    def to_json(self) -> dict:
        return {
            "id": str(self.id),
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "sequence": self.sequence,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "schema_version": self.schema_version,
            "payload": self.payload,
        }

    @classmethod
    def from_json(cls, data: dict) -> "SessionEntry":
        parent_id = data.get("parent_id")
        return cls(
            id=UUID(str(data["id"])),
            sequence=int(data["sequence"]),
            parent_id=UUID(str(parent_id)) if parent_id else None,
            type=EntryType(str(data.get("type", EntryType.MESSAGE.value))),
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            payload=dict(data.get("payload") or {}),
            schema_version=int(data.get("schema_version", 1)),
        )


def normalize_title(title: str) -> str:
    normalized = " ".join((title or "").split())
    if not normalized:
        raise ValueError("会话标题不能为空")
    return normalized[:TITLE_MAX_LENGTH]


def normalize_message(content: str) -> str:
    normalized = (content or "").strip()
    if not normalized:
        raise ValueError("消息内容不能为空")
    if len(normalized) > MESSAGE_MAX_LENGTH:
        raise ValueError(f"消息不能超过 {MESSAGE_MAX_LENGTH} 个字符")
    return normalized
