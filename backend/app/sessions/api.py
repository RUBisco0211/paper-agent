from uuid import UUID

from fastapi import APIRouter, Response, status

from ..agent.catalog import model_catalog
from ..auth.depends import CurrentUser
from ..platform.pagination import Page, PageParamsDep
from .depends import SessionBindingServiceDep
from .schemas import (
    BoundCitationRead,
    LlmCatalogResponse,
    SessionBindingCreateRequest,
    SessionBindingRead,
    to_llm_catalog,
)

bindings_router = APIRouter(prefix="/session-bindings", tags=["sessions"])
settings_router = APIRouter(tags=["agent"])


@bindings_router.post(
    "", response_model=SessionBindingRead, status_code=status.HTTP_201_CREATED
)
def create_session_binding(
    payload: SessionBindingCreateRequest,
    user: CurrentUser,
    service: SessionBindingServiceDep,
) -> SessionBindingRead:
    binding = service.create(
        session_id=payload.session_id,
        user_id=user.id,
        project_id=payload.project_id,
    )
    return SessionBindingRead(
        session_id=binding.session_id,
        project_id=binding.project_id,
        scope="project" if binding.project_id else "library",
    )


@bindings_router.get("", response_model=Page[SessionBindingRead])
def list_session_bindings(
    user: CurrentUser,
    params: PageParamsDep,
    service: SessionBindingServiceDep,
) -> Page[SessionBindingRead]:
    records, total = service.list_for_user(
        user_id=user.id, limit=params.limit, offset=params.offset
    )
    return Page.create(
        [
            SessionBindingRead(
                session_id=record.session_id,
                project_id=record.project_id,
                scope="project" if record.project_id else "library",
            )
            for record in records
        ],
        total=total,
        params=params,
    )


@bindings_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session_binding(
    session_id: UUID,
    user: CurrentUser,
    service: SessionBindingServiceDep,
) -> Response:
    service.delete(session_id=session_id, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@bindings_router.get(
    "/{session_id}/citations/{citation_id}", response_model=BoundCitationRead
)
def read_bound_citation(
    session_id: UUID,
    citation_id: str,
    user: CurrentUser,
    service: SessionBindingServiceDep,
) -> BoundCitationRead:
    citation = service.require_citation(
        session_id=session_id, user_id=user.id, citation_id=citation_id
    )
    return BoundCitationRead(
        citation_id=citation.citation_id,
        paper_id=citation.user_paper_id,
        title_path=citation.title_path,
        snippet=citation.snippet,
        page_start=citation.page_start,
        page_end=citation.page_end,
        chunk_ids=citation.chunk_ids,
        source_locations=citation.source_locations or [],
    )


@settings_router.get(
    "/llm-catalog",
    response_model=LlmCatalogResponse,
    summary="读取可选择的 LLM Provider 与模型目录",
)
def read_llm_catalog(user: CurrentUser) -> LlmCatalogResponse:
    return to_llm_catalog(model_catalog())
