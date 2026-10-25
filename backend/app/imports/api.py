from uuid import UUID

from fastapi import APIRouter, status

from ..auth.depends import CurrentUser
from ..platform.internal_auth import AgentInternalAuth
from .depends import DiscoveryServiceDep, ImportApprovalServiceDep, ImportServiceDep
from .schemas import (
    BatchImportRead,
    BoundBatchImportRequest,
    DiscoveryRequest,
    DiscoveryResponse,
    ImportApprovalPreview,
    ImportApprovalRead,
    ImportApprovalRequest,
    ImportQueueRead,
    ImportRead,
    ImportRequest,
    ManualDiscoveryRequest,
)

router = APIRouter(prefix="/imports", tags=["imports"])


def _read(record, service, user_id: UUID) -> ImportRead:
    """Project one import, resolving the user's entry once it is ready."""
    return ImportRead.from_domain(
        record,
        user_paper_id=service.entry_id_for(record=record, user_id=user_id),
    )
internal_router = APIRouter(tags=["imports"])


@internal_router.post("/discover-papers", response_model=DiscoveryResponse)
def discover_papers_manually(
    payload: ManualDiscoveryRequest,
    _user: CurrentUser,
    service: DiscoveryServiceDep,
) -> DiscoveryResponse:
    return DiscoveryResponse(
        **service.search_manual(query=payload.query, limit=payload.limit)
    )


@internal_router.post("/internal/discover-papers", response_model=DiscoveryResponse)
def discover_papers(
    payload: DiscoveryRequest,
    _auth: AgentInternalAuth,
    service: DiscoveryServiceDep,
) -> DiscoveryResponse:
    return DiscoveryResponse(
        **service.search(
            user_id=payload.user_id,
            session_id=payload.session_id,
            query=payload.query,
            limit=payload.limit,
        )
    )


@router.get("/queue", response_model=ImportQueueRead)
def read_import_queue(user: CurrentUser, service: ImportServiceDep) -> ImportQueueRead:
    return ImportQueueRead.model_validate({"items": service.queue(user_id=user.id)})


@router.post("/approvals", response_model=ImportApprovalRead, status_code=201)
def approve_batch(
    payload: ImportApprovalRequest,
    user: CurrentUser,
    service: ImportApprovalServiceDep,
) -> ImportApprovalRead:
    record = service.approve(
        user_id=user.id,
        session_id=payload.session_id,
        candidate_tokens=payload.candidate_tokens,
    )
    return ImportApprovalRead(id=record.id, count=len(record.candidates))


@router.get("/approvals/latest", response_model=ImportApprovalPreview)
def preview_batch(
    session_id: UUID, user: CurrentUser, service: ImportApprovalServiceDep
) -> ImportApprovalPreview:
    return ImportApprovalPreview(
        candidates=service.preview(user_id=user.id, session_id=session_id)
    )


@internal_router.post("/internal/import-approved", response_model=BatchImportRead)
def import_approved_batch(
    payload: BoundBatchImportRequest,
    _auth: AgentInternalAuth,
    service: ImportApprovalServiceDep,
) -> BatchImportRead:
    return BatchImportRead(
        results=service.consume(user_id=payload.user_id, session_id=payload.session_id)
    )


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
    )
    return _read(record, service, user.id)


@router.post(
    "/{import_id}/retry",
    response_model=ImportRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重试未完成的入库",
)
def retry_import(
    import_id: UUID,
    user: CurrentUser,
    service: ImportServiceDep,
) -> ImportRead:
    """Re-run what did not finish; stages whose output exists are skipped."""
    service.get(user_id=user.id, import_id=import_id)
    return _read(service.retry_import(import_id), service, user.id)


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
    record = service.get(user_id=user.id, import_id=import_id)
    return _read(record, service, user.id)
