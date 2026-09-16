"""Cross-domain HTTP wiring: root router and shared response models."""

from fastapi import APIRouter

from .auth import auth_router
from .ingestion import ingestion_router
from .library import library_router
from .platform.config import settings
from .projects import projects_router
from .retrieval import retrieval_router
from .sessions import sessions_router


def build_api_router() -> APIRouter:
    """Assemble the versioned API from every domain module."""
    router = APIRouter(prefix=settings.api_prefix)
    router.include_router(auth_router)
    router.include_router(library_router)
    router.include_router(ingestion_router)
    router.include_router(projects_router)
    router.include_router(retrieval_router)
    router.include_router(sessions_router)
    return router
