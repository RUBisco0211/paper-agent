"""Cross-domain HTTP wiring: root router and shared response models.

Routers are imported from their concrete modules (not through package
``__init__``) so importing a domain's persistence never pulls in the HTTP layer
and no import cycle can form.
"""

from fastapi import APIRouter

from .auth.api import router as auth_router
from .imports.api import router as imports_router
from .ingestion.api import router as ingestion_router
from .library.api import router as library_router
from .platform.config import settings
from .projects.api import router as projects_router
from .retrieval.api import router as retrieval_router
from .sessions.api import router as sessions_router
from .sessions.api import bindings_router
from .sessions.api import settings_router as agent_settings_router


def build_api_router() -> APIRouter:
    """Assemble the versioned API from every domain module."""
    router = APIRouter(prefix=settings.api_prefix)
    router.include_router(auth_router)
    router.include_router(imports_router)
    router.include_router(library_router)
    router.include_router(ingestion_router)
    router.include_router(projects_router)
    router.include_router(retrieval_router)
    router.include_router(sessions_router)
    router.include_router(bindings_router)
    router.include_router(agent_settings_router)
    return router
