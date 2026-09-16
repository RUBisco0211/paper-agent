from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .application import MessageSubmission, ResumeOutcome
from .domain import Delivery, EntryType, PendingMessage, Session, SessionEntry


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    project_id: UUID | None = None


class SessionUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class PendingCountsRead(BaseModel):
    steering: int = 0
    follow_up: int = 0


class PendingMessageRead(BaseModel):
    id: UUID
    delivery: Delivery
    position: int
    content: str
    created_at: datetime


class SessionRead(BaseModel):
    id: UUID
    title: str | None = None
    scope: str
    project_id: UUID | None = None
    pending: PendingCountsRead
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionRead):
    pending_messages: list[PendingMessageRead] = []


class SessionEntryRead(BaseModel):
    id: UUID
    sequence: int
    parent_id: UUID | None = None
    type: EntryType
    timestamp: datetime
    schema_version: int
    payload: dict


def to_session_read(session: Session, counts: dict[str, int]) -> SessionRead:
    return SessionRead(
        id=session.id,
        title=session.title,
        scope=session.scope,
        project_id=session.project_id,
        pending=PendingCountsRead(
            steering=counts.get("steering", 0),
            follow_up=counts.get("follow_up", 0),
        ),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def to_pending_read(pending: PendingMessage) -> PendingMessageRead:
    return PendingMessageRead(
        id=pending.id,
        delivery=pending.delivery,
        position=pending.position,
        content=pending.content,
        created_at=pending.created_at,
    )


def to_entry_read(entry: SessionEntry) -> SessionEntryRead:
    return SessionEntryRead(
        id=entry.id,
        sequence=entry.sequence,
        parent_id=entry.parent_id,
        type=entry.type,
        timestamp=entry.timestamp,
        schema_version=entry.schema_version,
        payload=entry.payload,
    )


class LlmConfigRequest(BaseModel):
    """Transient LLM configuration supplied by the browser per submission."""

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(min_length=1, max_length=512, repr=False)


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    delivery: Delivery | None = None
    llm_config: LlmConfigRequest | None = None


class MessageAcceptedResponse(BaseModel):
    """Either an immediate user entry or a queued message; never both."""

    entry: SessionEntryRead | None = None
    pending: PendingMessageRead | None = None
    generation_started: bool = False


class ResumeRequest(BaseModel):
    llm_config: LlmConfigRequest


class ResumeResponse(BaseModel):
    delivered: SessionEntryRead
    pending: PendingCountsRead


def to_message_response(submission: MessageSubmission) -> MessageAcceptedResponse:
    return MessageAcceptedResponse(
        entry=to_entry_read(submission.entry) if submission.entry else None,
        pending=to_pending_read(submission.pending) if submission.pending else None,
        generation_started=submission.generation_started,
    )


def to_resume_response(outcome: ResumeOutcome) -> ResumeResponse:
    assert outcome.delivered is not None
    return ResumeResponse(
        delivered=to_entry_read(outcome.delivered),
        pending=PendingCountsRead(
            steering=outcome.remaining.get("steering", 0),
            follow_up=outcome.remaining.get("follow_up", 0),
        ),
    )
