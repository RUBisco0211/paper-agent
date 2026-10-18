from uuid import UUID

from fastapi import APIRouter, Response, status

from ..auth.depends import CurrentUser
from ..library.schemas import UserPaperSummary, to_summary
from ..platform.pagination import Page, PageParamsDep
from .depends import ProjectServiceDep
from .domain import Project
from .schemas import (
    ProjectCreateRequest,
    ProjectPapersAddRequest,
    ProjectPapersAddResponse,
    ProjectRead,
    ProjectUpdateRequest,
)
from .service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_schema(project: Project, *, paper_count: int) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        paper_count=paper_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _require_project(
    service: ProjectService,
    *,
    user_id: UUID,
    project_id: UUID,
) -> Project:
    return service.get(user_id=user_id, project_id=project_id)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建项目",
)
def create_project(
    payload: ProjectCreateRequest,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    project = service.create(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
    )
    return _project_schema(project, paper_count=0)


@router.get(
    "",
    response_model=Page[ProjectRead],
    summary="列出当前用户的项目",
)
def list_projects(
    user: CurrentUser,
    params: PageParamsDep,
    service: ProjectServiceDep,
) -> Page[ProjectRead]:
    projects, total = service.list_projects(
        user_id=user.id,
        limit=params.limit,
        offset=params.offset,
    )
    return Page.create(
        [_project_schema(project, paper_count=count) for project, count in projects],
        total=total,
        params=params,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="读取项目详情",
)
def read_project(
    project_id: UUID,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    project = _require_project(service, user_id=user.id, project_id=project_id)
    return _project_schema(project, paper_count=service.paper_count(project_id))


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="修改项目名称或描述",
)
def update_project(
    project_id: UUID,
    payload: ProjectUpdateRequest,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectRead:
    project = service.rename(
        user_id=user.id,
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        clear_description=(
            "description" in payload.model_fields_set and payload.description is None
        ),
    )
    return _project_schema(project, paper_count=service.paper_count(project_id))


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除项目（论文保留在个人论文库）",
)
def delete_project(
    project_id: UUID,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> Response:
    service.delete(user_id=user.id, project_id=project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project_id}/papers",
    response_model=Page[UserPaperSummary],
    summary="列出项目论文",
)
def list_project_papers(
    project_id: UUID,
    user: CurrentUser,
    params: PageParamsDep,
    service: ProjectServiceDep,
    q: str | None = None,
) -> Page[UserPaperSummary]:
    entries, total = service.list_papers(
        user_id=user.id,
        project_id=project_id,
        query=q,
        limit=params.limit,
        offset=params.offset,
    )
    return Page.create(
        [to_summary(entry) for entry in entries], total=total, params=params
    )


@router.post(
    "/{project_id}/papers",
    response_model=ProjectPapersAddResponse,
    status_code=status.HTTP_201_CREATED,
    summary="从个人论文库向项目追加论文",
)
def add_project_papers(
    project_id: UUID,
    payload: ProjectPapersAddRequest,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectPapersAddResponse:
    result = service.add_papers(
        user_id=user.id,
        project_id=project_id,
        user_paper_ids=payload.paper_ids,
    )
    return ProjectPapersAddResponse(
        added=[to_summary(entry) for entry in result.added],
        already_present=result.already_present,
    )
