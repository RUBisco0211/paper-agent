from uuid import UUID

from fastapi import APIRouter, status

from ..auth.depends import CurrentUser
from ..platform.errors import ErrorCode, NotFoundError
from .depends import IngestionServiceDep
from .schemas import IngestionJobRead

router = APIRouter(prefix="/ingestion-jobs", tags=["ingestion"])


@router.get(
    "/{job_id}",
    response_model=IngestionJobRead,
    summary="读取处理任务与各阶段状态",
)
def read_ingestion_job(
    job_id: UUID,
    user: CurrentUser,
    service: IngestionServiceDep,
) -> IngestionJobRead:
    job = service.get_job(job_id)
    if job is None:
        raise NotFoundError(
            "处理任务不存在",
            code=ErrorCode.INGESTION_JOB_NOT_FOUND,
        )
    return IngestionJobRead.from_domain(
        job,
        user_paper_id=service.user_paper_id(
            job_paper_id=job.paper_id,
            user_id=user.id,
        ),
    )


@router.post(
    "/{job_id}/retry",
    response_model=IngestionJobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重试失败或未完成的处理阶段",
)
def retry_ingestion_job(
    job_id: UUID,
    user: CurrentUser,
    service: IngestionServiceDep,
) -> IngestionJobRead:
    job = service.get_job(job_id)
    if job is None:
        raise NotFoundError(
            "处理任务不存在",
            code=ErrorCode.INGESTION_JOB_NOT_FOUND,
        )
    user_paper_id = service.user_paper_id(
        job_paper_id=job.paper_id,
        user_id=user.id,
    )
    new_job = service.retry_job(job_id)
    return IngestionJobRead.from_domain(new_job, user_paper_id=user_paper_id)
