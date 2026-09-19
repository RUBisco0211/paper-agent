from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .application import MessageSubmission, ResumeOutcome, SessionView
from .domain import (
    Citation,
    Delivery,
    EntryType,
    PendingMessage,
    SessionEntry,
)
from .model_catalog import ProviderOption


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    project_id: UUID | None = None
    paper_id: UUID | None = Field(
        default=None,
        description="单篇文献会话的条目 ID；与 project_id 互斥",
    )


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
    #: library = 全局；project = 项目；paper = 单篇文献
    scope: str
    project_id: UUID | None = None
    paper_id: UUID | None = None
    pending: PendingCountsRead
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionRead):
    pending_messages: list[PendingMessageRead] = []
    """Whether an assistant turn is running right now.

    The UI uses this to decide between starting a generation and queueing input;
    it is runtime state, not persisted history.
    """
    is_generating: bool = False


class SessionEntryRead(BaseModel):
    id: UUID
    sequence: int
    parent_id: UUID | None = None
    type: EntryType
    timestamp: datetime
    schema_version: int
    payload: dict


def to_session_read(view: SessionView) -> SessionRead:
    """范围来自会话上下文（单篇文献会话不在数据库里建关联）。"""
    return SessionRead(
        id=view.session.id,
        title=view.session.title,
        scope=view.context.scope,
        project_id=view.session.project_id,
        paper_id=view.context.paper_id,
        pending=PendingCountsRead(
            steering=view.pending_counts.get("steering", 0),
            follow_up=view.pending_counts.get("follow_up", 0),
        ),
        created_at=view.session.created_at,
        updated_at=view.session.updated_at,
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


class LlmModelRead(BaseModel):
    id: str
    label: str
    context_size: int | None = None
    reasoning_efforts: list[str] = []


class LlmProviderRead(BaseModel):
    id: str
    label: str
    models: list[LlmModelRead]


class LlmCatalogResponse(BaseModel):
    providers: list[LlmProviderRead]


def to_llm_catalog(providers: tuple[ProviderOption, ...]) -> LlmCatalogResponse:
    return LlmCatalogResponse(
        providers=[
            LlmProviderRead(
                id=provider.id,
                label=provider.label,
                models=[
                    LlmModelRead(
                        id=model.id,
                        label=model.label,
                        context_size=model.context_size,
                        reasoning_efforts=list(model.reasoning_efforts),
                    )
                    for model in provider.models
                ],
            )
            for provider in providers
        ],
    )


class LlmConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(min_length=1, max_length=512, repr=False)
    reasoning_effort: str | None = Field(default=None, max_length=20)


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    delivery: Delivery | None = None
    llm_config: LlmConfigRequest | None = None


class MessageAcceptedResponse(BaseModel):
    """Either an immediate user entry or a queued message; never both."""

    entry: SessionEntryRead | None = None
    pending: PendingMessageRead | None = None
    generation_started: bool = False


class ResumeResponse(BaseModel):
    delivered: SessionEntryRead
    pending: PendingCountsRead


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_config: LlmConfigRequest


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


class CitationRead(BaseModel):
    """Evidence behind one citation; ``paper_id`` is the user's entry id."""

    citation_id: str
    paper_id: UUID
    title_path: str | None = None
    snippet: str
    page_start: int | None = None
    page_end: int | None = None
    chunk_ids: list[UUID] = []


def to_citation_read(citation: Citation) -> CitationRead:
    return CitationRead(
        citation_id=citation.citation_id,
        paper_id=citation.user_paper_id,
        title_path=citation.title_path,
        snippet=citation.snippet,
        page_start=citation.page_start,
        page_end=citation.page_end,
        chunk_ids=citation.chunk_ids,
    )
