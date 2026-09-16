from uuid import UUID

from fastapi import APIRouter, status

from ..auth.dependencies import CurrentUser
from .dependencies import ImportServiceDep
from .schemas import ImportRead, ImportRequest

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "",
    response_model=ImportRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="按 DOI/arXiv 导入论文（先元数据，再尝试获取全文）",
)
def start_import(
    payload: ImportRequest,
    user: CurrentUser,
    service: ImportServiceDep,
) -> ImportRead:
    record = service.start(
        user_id=user.id,
        identifier_text=payload.identifier,
        project_id=payload.project_id,
    )
    return ImportRead.from_domain(record)


@router.get(
    "/{import_id}",
    response_model=ImportRead,
    summary="读取导入进度",
)
def read_import(
    import_id: UUID,
    user: CurrentUser,
    service: ImportServiceDep,
) -> ImportRead:
    return ImportRead.from_domain(
        service.get(user_id=user.id, import_id=import_id),
    )
