from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from ..auth.dependencies import CurrentUser
from ..ingestion.domain import IngestionJob
from ..ingestion.schemas import IngestionJobRead
from ..platform.errors import ErrorCode, NotFoundError
from ..platform.pagination import Page, PageParamsDep
from .application import MetadataCorrection
from .dependencies import PaperLibraryServiceDep
from .schemas import (
    FetchPdfResponse,
    MetadataCompletionRead,
    MetadataCorrectionRequest,
    ResolveMetadataResponse,
    UploadResponse,
    UserPaperDetail,
    UserPaperSummary,
    to_detail,
    to_summary,
)

router = APIRouter(prefix="/papers", tags=["library"])


def _job_schema(
    job: IngestionJob | None,
    *,
    user_paper_id: UUID,
) -> IngestionJobRead | None:
    if job is None:
        return None
    return IngestionJobRead.from_domain(job, user_paper_id=user_paper_id)


@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="上传 PDF 并创建个人论文条目",
)
def upload_paper(
    user: CurrentUser,
    service: PaperLibraryServiceDep,
    file: Annotated[UploadFile, File(description="英文 born-digital PDF")],
) -> UploadResponse:
    entry, job = service.upload_pdf(
        user_id=user.id,
        filename=file.filename,
        stream=file.file,
    )
    return UploadResponse(
        paper=to_summary(entry),
        ingestion_job=_job_schema(job, user_paper_id=entry.user_paper.id),
    )


@router.get(
    "",
    response_model=Page[UserPaperSummary],
    summary="列出个人论文库条目",
)
def list_papers(
    user: CurrentUser,
    params: PageParamsDep,
    service: PaperLibraryServiceDep,
    q: Annotated[str | None, Query(description="按标题过滤")] = None,
) -> Page[UserPaperSummary]:
    entries, total = service.list_entries(
        user_id=user.id,
        limit=params.limit,
        offset=params.offset,
        query=q,
    )
    return Page.create(
        [to_summary(entry) for entry in entries],
        total=total,
        params=params,
    )


def _entry_or_404(
    service: PaperLibraryServiceDep,
    *,
    user_id: UUID,
    user_paper_id: UUID,
):
    entry = service.get_entry(user_id=user_id, user_paper_id=user_paper_id)
    if entry is None:
        raise NotFoundError("论文不存在", code=ErrorCode.PAPER_NOT_FOUND)
    return entry


@router.get(
    "/{paper_id}",
    response_model=UserPaperDetail,
    summary="读取论文详情与当前能力",
)
def read_paper(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
) -> UserPaperDetail:
    entry = _entry_or_404(service, user_id=user.id, user_paper_id=paper_id)
    return to_detail(entry)


@router.get(
    "/{paper_id}/pdf",
    response_class=StreamingResponse,
    summary="读取授权范围内的论文原文",
)
def read_paper_pdf(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
) -> StreamingResponse:
    entry = _entry_or_404(service, user_id=user.id, user_paper_id=paper_id)
    stream = service.get_pdf_stream(user_id=user.id, user_paper_id=paper_id)
    filename = f"{entry.user_paper.id}.pdf"
    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=0, must-revalidate",
        },
    )


@router.post(
    "/{paper_id}/pdf",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="为已有条目补传或替换 PDF",
)
def attach_paper_pdf(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
    file: Annotated[UploadFile, File(description="英文 born-digital PDF")],
) -> UploadResponse:
    entry, job = service.attach_pdf(
        user_id=user.id,
        user_paper_id=paper_id,
        filename=file.filename,
        stream=file.file,
    )
    return UploadResponse(
        paper=to_summary(entry),
        ingestion_job=_job_schema(job, user_paper_id=entry.user_paper.id),
    )


@router.post(
    "/{paper_id}/fetch-pdf",
    response_model=FetchPdfResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="按标识符重新尝试获取公开 PDF",
)
def fetch_paper_pdf(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
) -> FetchPdfResponse:
    entry, job, completion = service.fetch_pdf(
        user_id=user.id,
        user_paper_id=paper_id,
    )
    return FetchPdfResponse(
        paper=to_summary(entry),
        ingestion_job=_job_schema(job, user_paper_id=entry.user_paper.id),
        metadata=MetadataCompletionRead(
            status=completion.status,
            source=completion.source,
            error_code=completion.error_code,
            applied_fields=list(completion.applied_fields),
        ),
    )


@router.patch(
    "/{paper_id}/metadata",
    response_model=UserPaperDetail,
    summary="修正当前用户条目的标识符与书目字段",
)
def patch_paper_metadata(
    paper_id: UUID,
    payload: MetadataCorrectionRequest,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
) -> UserPaperDetail:
    entry = service.update_metadata(
        user_id=user.id,
        user_paper_id=paper_id,
        correction=MetadataCorrection(
            title=payload.title,
            authors=payload.authors,
            abstract=payload.abstract,
            doi=payload.doi,
            arxiv_id=payload.arxiv_id,
            year=payload.year,
            venue=payload.venue,
        ),
    )
    return to_detail(entry)


@router.post(
    "/{paper_id}/resolve-metadata",
    response_model=ResolveMetadataResponse,
    summary="按标识符精确补全元数据",
)
def resolve_paper_metadata(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
) -> ResolveMetadataResponse:
    completion = service.complete_metadata(
        user_id=user.id,
        user_paper_id=paper_id,
    )
    return ResolveMetadataResponse(
        paper=to_detail(completion.entry),
        metadata=MetadataCompletionRead(
            status=completion.status,
            source=completion.source,
            error_code=completion.error_code,
            applied_fields=list(completion.applied_fields),
        ),
    )
