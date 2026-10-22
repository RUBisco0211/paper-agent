from typing import Annotated

from fastapi import Depends

from ..platform.config import settings
from ..platform.database import SessionDep
from .crypto import CredentialCipher
from .repo import ServiceCredentialRepository
from .service import ServiceCredentialService


def get_credential_cipher() -> CredentialCipher:
    """Build the cipher once per request from the instance master key."""
    return CredentialCipher(settings.credential_master_key.get_secret_value())


CredentialCipherDep = Annotated[CredentialCipher, Depends(get_credential_cipher)]


def get_service_credential_service(
    session: SessionDep,
    cipher: CredentialCipherDep,
) -> ServiceCredentialService:
    return ServiceCredentialService(ServiceCredentialRepository(session), cipher)


ServiceCredentialServiceDep = Annotated[
    ServiceCredentialService, Depends(get_service_credential_service)
]
