from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ..auth.dependencies import CurrentUser
from ..platform.config import settings
from ..platform.pagination import Page, PageParamsDep
from .agent import validate_llm_config
from .dependencies import CitationServiceDep, SessionServiceDep, SseIdleTimeoutDep
from .domain import Session
from .schemas import (
    CitationRead,
    MessageAcceptedResponse,
    MessageRequest,
    ResumeRequest,
    ResumeResponse,
    SessionCreateRequest,
    SessionDetail,
    SessionEntryRead,
    SessionRead,
    SessionUpdateRequest,
    to_citation_read,
    to_entry_read,
    to_message_response,
    to_pending_read,
    to_resume_response,
    to_session_read,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings_router = APIRouter(tags=["agent"])


@router.post(
    "",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建会话（个人全库或项目范围）",
)
def create_session(
    payload: SessionCreateRequest,
    user: CurrentUser,
    service: SessionServiceDep,
) -> SessionRead:
    session = service.create(
        user_id=user.id,
        title=payload.title,
        project_id=payload.project_id,
        paper_id=payload.paper_id,
    )
    return to_session_read(service.view_for(session))


@router.get(
    "",
    response_model=Page[SessionRead],
    summary="列出会话",
)
def list_sessions(
    user: CurrentUser,
    params: PageParamsDep,
    service: SessionServiceDep,
    scope: Annotated[Literal["library", "project", "paper"], Query()] = "library",
    project_id: Annotated[UUID | None, Query()] = None,
    paper_id: Annotated[UUID | None, Query()] = None,
) -> Page[SessionRead]:
    views, total = service.list_sessions(
        user_id=user.id,
        limit=params.limit,
        offset=params.offset,
        project_id=project_id,
        library_only=scope == "library",
        paper_only=scope == "paper",
        paper_id=paper_id,
    )
    return Page.create(
        [to_session_read(view) for view in views],
        total=total,
        params=params,
    )


@router.get(
    "/{session_id}",
    response_model=SessionDetail,
    summary="读取会话详情与待投递消息快照",
)
def read_session(
    session_id: UUID,
    user: CurrentUser,
    service: SessionServiceDep,
) -> SessionDetail:
    session = service.get(user_id=user.id, session_id=session_id)
    pending = service.pending_snapshot(session_id)
    counts = {"steering": 0, "follow_up": 0}
    for item in pending:
        counts[item.delivery.value] = counts.get(item.delivery.value, 0) + 1
    base = to_session_read(service.view_for(session)).model_dump()
    return SessionDetail(
        **base,
        pending_messages=[to_pending_read(item) for item in pending],
        is_generating=service.is_generating(session_id),
    )


@router.patch(
    "/{session_id}",
    response_model=SessionRead,
    summary="修改会话标题",
)
def update_session(
    session_id: UUID,
    payload: SessionUpdateRequest,
    user: CurrentUser,
    service: SessionServiceDep,
) -> SessionRead:
    session = service.rename(
        user_id=user.id,
        session_id=session_id,
        title=payload.title,
    )
    return to_session_read(service.view_for(session))


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除会话及其历史",
)
def delete_session(
    session_id: UUID,
    user: CurrentUser,
    service: SessionServiceDep,
) -> Response:
    service.delete(user_id=user.id, session_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{session_id}/entries",
    response_model=Page[SessionEntryRead],
    summary="按游标读取会话历史",
)
def list_session_entries(
    session_id: UUID,
    user: CurrentUser,
    params: PageParamsDep,
    service: SessionServiceDep,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
) -> Page[SessionEntryRead]:
    _, entries = service.list_entries(
        user_id=user.id,
        session_id=session_id,
        after_sequence=after_sequence,
        limit=params.limit,
    )
    return Page.create(
        [to_entry_read(entry) for entry in entries],
        total=len(entries),
        params=params,
    )


def get_event_session(
    session_id: UUID,
    user: CurrentUser,
    service: SessionServiceDep,
) -> Session:
    """Authorize before the stream starts, so failures stay normal responses."""
    return service.get(user_id=user.id, session_id=session_id)


@router.post(
    "/{session_id}/messages",
    response_model=MessageAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交用户消息（空闲时立即开始生成，生成中则进入队列）",
)
def submit_message(
    session_id: UUID,
    payload: MessageRequest,
    user: CurrentUser,
    service: SessionServiceDep,
) -> MessageAcceptedResponse:
    llm_config = (
        validate_llm_config(
            provider=payload.llm_config.provider,
            model=payload.llm_config.model,
            api_key=payload.llm_config.api_key,
        )
        if payload.llm_config
        else None
    )
    submission = service.submit_message(
        user_id=user.id,
        session_id=session_id,
        content=payload.content,
        delivery=payload.delivery,
        llm_config=llm_config,
    )
    return to_message_response(submission)


@router.post(
    "/{session_id}/stop",
    status_code=status.HTTP_202_ACCEPTED,
    summary="停止当前生成（保留已生成内容与队列）",
)
def stop_generation(
    session_id: UUID,
    user: CurrentUser,
    service: SessionServiceDep,
) -> dict[str, bool]:
    service.stop(user_id=user.id, session_id=session_id)
    return {"stopped": True}


@router.post(
    "/{session_id}/resume",
    response_model=ResumeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重新提供 LLM 配置并继续消费排队消息",
)
def resume_session(
    session_id: UUID,
    payload: ResumeRequest,
    user: CurrentUser,
    service: SessionServiceDep,
) -> ResumeResponse:
    llm_config = validate_llm_config(
        provider=payload.llm_config.provider,
        model=payload.llm_config.model,
        api_key=payload.llm_config.api_key,
    )
    outcome = service.resume(
        user_id=user.id,
        session_id=session_id,
        llm_config=llm_config,
    )
    return to_resume_response(outcome)


@router.get(
    "/{session_id}/events",
    response_class=EventSourceResponse,
    summary="订阅会话事件流（支持事件游标重放）",
)
async def stream_session_events(
    session_id: UUID,
    session: Annotated[Session, Depends(get_event_session)],
    service: SessionServiceDep,
    idle_timeout: SseIdleTimeoutDep,
    request: Request,
    last_event_id: Annotated[str | None, Query(alias="last_event_id")] = None,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
) -> AsyncIterator[ServerSentEvent]:
    cursor = after_sequence
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    stream = service.event_stream(
        session_id=session.id,
        after_sequence=cursor,
        idle_timeout_seconds=idle_timeout,
    )
    async for event in stream:
        if await request.is_disconnected():
            break
        if event is None:
            # ``None`` is an idle poll; FastAPI turns this into a keep-alive
            # comment so proxies do not drop a quiet connection.
            yield ServerSentEvent(comment="keep-alive")
            continue
        yield ServerSentEvent(
            event=event.type,
            id=str(event.sequence),
            data=event.to_payload(),
        )


@router.get(
    "/{session_id}/citations/{citation_id}",
    response_model=CitationRead,
    summary="按会话与该用户校验后展开引用证据",
)
def read_citation(
    session_id: UUID,
    citation_id: str,
    user: CurrentUser,
    service: CitationServiceDep,
) -> CitationRead:
    citation = service.get(
        user_id=user.id,
        session_id=session_id,
        citation_id=citation_id,
    )
    return to_citation_read(citation)


@settings_router.get(
    "/llm-providers",
    summary="列出允许使用的 LLM Provider（不含 Base URL 与任何凭据）",
)
def list_llm_providers() -> dict[str, list[str]]:
    return {"providers": sorted(settings.llm_providers)}
