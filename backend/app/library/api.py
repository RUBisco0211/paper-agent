import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from app.processing.domain import IngestionJob
from app.processing.schemas import IngestionJobRead

from ..auth.depends import CurrentUser
from ..platform.errors import ErrorCode, NotFoundError
from ..platform.pagination import Page, PageParamsDep
from .depends import PaperLibraryServiceDep
from .schemas import (
    FetchMetadataResponse,
    FetchPdfResponse,
    MetadataFetchRead,
    PaperBlockRead,
    PaperBlocksResponse,
    PaperInfoUpdateRequest,
    UploadResponse,
    UserPaperDetail,
    UserPaperSummary,
    to_detail,
    to_summary,
)
from .service import PaperInfoUpdate

router = APIRouter(prefix="/papers", tags=["library"])
CACHE_CONTROL = "private, no-cache"


def _cache_tag(*parts: object) -> str:
    digest = hashlib.sha256("\x00".join(map(str, parts)).encode()).hexdigest()
    return f'"{digest}"'


def _cache_headers(etag: str) -> dict[str, str]:
    return {"Cache-Control": CACHE_CONTROL, "ETag": etag}


def _matches_cache(request: Request, etag: str) -> bool:
    supplied = request.headers.get("If-None-Match", "")
    return any(
        tag.strip().removeprefix("W/") in {etag, "*"} for tag in supplied.split(",")
    )


@router.get("/{paper_id}/blocks", response_model=PaperBlocksResponse)
def list_paper_blocks(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
    request: Request,
    response: Response,
    block_type: Annotated[str | None, Query(alias="type")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaperBlocksResponse | Response:
    result = PaperBlocksResponse.model_validate(
        service.list_blocks(
            user_id=user.id,
            user_paper_id=paper_id,
            block_type=block_type,
            offset=offset,
            limit=limit,
        )
    )
    version = service.artifact_cache_version(user_id=user.id, user_paper_id=paper_id)
    if version is not None:
        etag = _cache_tag("blocks-v1", version, block_type, offset, limit)
        if _matches_cache(request, etag):
            return Response(status_code=304, headers=_cache_headers(etag))
        response.headers.update(_cache_headers(etag))
    return result


@router.get("/{paper_id}/blocks/{block_id}", response_model=PaperBlockRead)
def read_paper_block(
    paper_id: UUID,
    block_id: int,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
    request: Request,
    response: Response,
) -> PaperBlockRead | Response:
    result = PaperBlockRead.model_validate(
        service.get_block(
            user_id=user.id,
            user_paper_id=paper_id,
            block_id=block_id,
        )
    )
    version = service.artifact_cache_version(user_id=user.id, user_paper_id=paper_id)
    if version is not None:
        etag = _cache_tag("block-v1", version, block_id)
        if _matches_cache(request, etag):
            return Response(status_code=304, headers=_cache_headers(etag))
        response.headers.update(_cache_headers(etag))
    return result


@router.get("/{paper_id}/blocks/{block_id}/image", response_class=Response)
def read_paper_block_image(
    paper_id: UUID,
    block_id: int,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
    request: Request,
) -> Response:
    payload, media_type = service.get_block_image(
        user_id=user.id,
        user_paper_id=paper_id,
        block_id=block_id,
    )
    version = service.artifact_cache_version(user_id=user.id, user_paper_id=paper_id)
    etag = _cache_tag("block-image-v1", version, block_id)
    headers = {**_cache_headers(etag), "X-Content-Type-Options": "nosniff"}
    if _matches_cache(request, etag):
        return Response(status_code=304, headers=headers)
    return Response(
        payload,
        media_type=media_type,
        headers=headers,
    )


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
    detail = to_detail(entry)
    if entry.paper is not None:
        detail.pdf_version = entry.paper.file_hash
        detail.artifact_version = service.artifact_cache_version(
            user_id=user.id, user_paper_id=paper_id
        )
    return detail


@router.get(
    "/{paper_id}/pdf",
    response_class=StreamingResponse,
    summary="读取授权范围内的论文原文",
)
def read_paper_pdf(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
    request: Request,
) -> Response:
    entry = _entry_or_404(service, user_id=user.id, user_paper_id=paper_id)
    version = service.pdf_cache_version(user_id=user.id, user_paper_id=paper_id)
    etag = _cache_tag("pdf-v1", version)
    if _matches_cache(request, etag):
        return Response(status_code=304, headers=_cache_headers(etag))
    stream = service.get_pdf_stream(user_id=user.id, user_paper_id=paper_id)
    filename = f"{entry.user_paper.id}.pdf"
    return StreamingResponse(
        stream,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            **_cache_headers(etag),
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
    entry, job, result = service.fetch_pdf(
        user_id=user.id,
        user_paper_id=paper_id,
    )
    return FetchPdfResponse(
        paper=to_summary(entry),
        ingestion_job=_job_schema(job, user_paper_id=entry.user_paper.id),
        metadata=MetadataFetchRead(
            status=result.status,
            source=result.source,
            error_code=result.error_code,
            applied_fields=list(result.applied_fields),
        ),
    )


@router.patch(
    "/{paper_id}/info",
    response_model=UserPaperDetail,
    summary="编辑当前用户条目的书目信息",
)
def update_paper_info(
    paper_id: UUID,
    payload: PaperInfoUpdateRequest,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
) -> UserPaperDetail:
    entry = service.update_info(
        user_id=user.id,
        user_paper_id=paper_id,
        update=PaperInfoUpdate(
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
    "/{paper_id}/fetch-metadata",
    response_model=FetchMetadataResponse,
    summary="按条目标识符获取元数据",
)
def fetch_paper_metadata(
    paper_id: UUID,
    user: CurrentUser,
    service: PaperLibraryServiceDep,
) -> FetchMetadataResponse:
    result = service.fetch_metadata(
        user_id=user.id,
        user_paper_id=paper_id,
    )
    return FetchMetadataResponse(
        paper=to_detail(result.entry),
        metadata=MetadataFetchRead(
            status=result.status,
            source=result.source,
            error_code=result.error_code,
            applied_fields=list(result.applied_fields),
        ),
    )
