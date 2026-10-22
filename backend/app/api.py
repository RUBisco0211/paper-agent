"""Cross-domain HTTP wiring: root router and shared response models.

Routers are imported from their concrete modules (not through package
``__init__``) so importing a domain's persistence never pulls in the HTTP layer
and no import cycle can form.
"""

from fastapi import APIRouter

from app.processing.api import router as processing_router

from .auth.api import internal_router as auth_internal_router
from .auth.api import router as auth_router
from .imports.api import internal_router as imports_internal_router
from .imports.api import router as imports_router
from .library.api import router as library_router
from .platform.config import settings
from .projects.api import router as projects_router
from .retrieval.api import router as retrieval_router
from .schedules.api import router as schedules_router
from .service_credentials.api import internal_router as credentials_internal_router
from .service_credentials.api import router as credentials_router
from .sessions.api import bindings_router
from .sessions.api import settings_router as agent_settings_router
from .web.api import internal_router as web_internal_router


def build_api_router() -> APIRouter:
    """Assemble the versioned API from every domain module."""
    router = APIRouter(prefix=settings.api_prefix)
    router.include_router(auth_router)
    router.include_router(auth_internal_router)
    router.include_router(imports_router)
    router.include_router(imports_internal_router)
    router.include_router(library_router)
    router.include_router(processing_router)
    router.include_router(projects_router)
    router.include_router(retrieval_router)
    router.include_router(schedules_router)
    router.include_router(bindings_router)
    router.include_router(agent_settings_router)
    router.include_router(credentials_router)
    router.include_router(credentials_internal_router)
    router.include_router(web_internal_router)
    return router
