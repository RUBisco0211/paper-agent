from typing import Annotated

from fastapi import Depends

from ..platform.database import SessionDep
from ..projects.repo import ProjectRepository
from .repo import SessionBindingRepository
from .service import SessionBindingService


def get_session_binding_service(session: SessionDep) -> SessionBindingService:
    return SessionBindingService(
        SessionBindingRepository(session), ProjectRepository(session)
    )


SessionBindingServiceDep = Annotated[
    SessionBindingService, Depends(get_session_binding_service)
]
