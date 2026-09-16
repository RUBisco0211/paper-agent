from uuid import UUID

from fastapi import APIRouter, status

from ..auth.dependencies import CurrentUser
from ..library.persistence import PaperRepository
from ..platform.database import SessionDep
from ..platform.errors import ErrorCode, NotFoundError
from .dependencies import IngestionServiceDep
from .schemas import IngestionJobRead

router = APIRouter(prefix="/ingestion-jobs", tags=["ingestion"])


def _user_paper_id(*, job_paper_id: UUID, user_id: UUID, session: SessionDep) -> UUID:
    """Map a shared paper to the requesting user's own entry id."""
    user_paper = PaperRepository(session).get_user_paper_for_paper(
        user_id=user_id,
        paper_id=job_paper_id,
    )
    if user_paper is None:
        # Same code as an unknown job: a job on another user's paper must not
        # reveal that the paper or the job exists.
        raise NotFoundError(
            "处理任务不存在",
            code=ErrorCode.INGESTION_JOB_NOT_FOUND,
        )
    return user_paper.id


@router.get(
    "/{job_id}",
    response_model=IngestionJobRead,
    summary="读取处理任务与各阶段状态",
)
def read_ingestion_job(
    job_id: UUID,
    user: CurrentUser,
    session: SessionDep,
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
        user_paper_id=_user_paper_id(
            job_paper_id=job.paper_id,
            user_id=user.id,
            session=session,
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
    session: SessionDep,
    service: IngestionServiceDep,
) -> IngestionJobRead:
    job = service.get_job(job_id)
    if job is None:
        raise NotFoundError(
            "处理任务不存在",
            code=ErrorCode.INGESTION_JOB_NOT_FOUND,
        )
    user_paper_id = _user_paper_id(
        job_paper_id=job.paper_id,
        user_id=user.id,
        session=session,
    )
    new_job = service.retry_job(job_id)
    return IngestionJobRead.from_domain(new_job, user_paper_id=user_paper_id)
