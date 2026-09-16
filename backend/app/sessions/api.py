from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from ..auth.dependencies import CurrentUser
from ..platform.pagination import Page, PageParamsDep
from .dependencies import SessionServiceDep
from .schemas import (
    SessionCreateRequest,
    SessionDetail,
    SessionEntryRead,
    SessionRead,
    SessionUpdateRequest,
    to_entry_read,
    to_pending_read,
    to_session_read,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


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
    )
    return to_session_read(session, {})


@router.get(
    "",
    response_model=Page[SessionRead],
    summary="列出会话",
)
def list_sessions(
    user: CurrentUser,
    params: PageParamsDep,
    service: SessionServiceDep,
    scope: Annotated[Literal["library", "project"], Query()] = "library",
    project_id: Annotated[UUID | None, Query()] = None,
) -> Page[SessionRead]:
    sessions, total = service.list_sessions(
        user_id=user.id,
        limit=params.limit,
        offset=params.offset,
        project_id=project_id,
        library_only=scope == "library",
    )
    return Page.create(
        [to_session_read(session, counts) for session, counts in sessions],
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
    base = to_session_read(
        session,
        {"steering": 0, "follow_up": 0},
    ).model_dump()
    return SessionDetail(
        **base,
        pending_messages=[to_pending_read(item) for item in pending],
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
    return to_session_read(session, {})


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
