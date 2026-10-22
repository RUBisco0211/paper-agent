from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel

from ..auth.depends import CurrentUser
from ..platform.internal_auth import AgentInternalAuth
from .depends import ServiceCredentialServiceDep
from .schemas import (
    ServiceCredentialListRead,
    ServiceCredentialRead,
    ServiceCredentialWrite,
)
from .service import require_secret

router = APIRouter(prefix="/service-credentials", tags=["service-credentials"])
internal_router = APIRouter(tags=["service-credentials"])


class SecretLookup(BaseModel):
    user_id: UUID
    kind: str
    field: str = "api_key"


@router.get("", response_model=ServiceCredentialListRead)
def list_credentials(
    user: CurrentUser,
    service: ServiceCredentialServiceDep,
) -> ServiceCredentialListRead:
    return ServiceCredentialListRead(
        items=[
            ServiceCredentialRead(kind=item.kind, label=item.label, fields=item.fields)
            for item in service.list(user.id)
        ]
    )


@router.put("/{kind}", response_model=ServiceCredentialRead)
def save_credential(
    kind: str,
    payload: ServiceCredentialWrite,
    user: CurrentUser,
    service: ServiceCredentialServiceDep,
) -> ServiceCredentialRead:
    view = service.save(user.id, kind, payload.label, payload.fields)
    return ServiceCredentialRead(kind=view.kind, label=view.label, fields=view.fields)


@router.delete("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    kind: str,
    user: CurrentUser,
    service: ServiceCredentialServiceDep,
) -> None:
    service.delete(user.id, kind)


@internal_router.post("/internal/service-credentials/secret")
def read_secret(
    payload: SecretLookup,
    _auth: AgentInternalAuth,
    service: ServiceCredentialServiceDep,
) -> dict[str, str]:
    return {
        "value": require_secret(service, payload.user_id, payload.kind, payload.field)
    }
