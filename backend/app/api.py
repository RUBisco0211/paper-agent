"""Cross-domain HTTP wiring: root router and shared response models."""

from fastapi import APIRouter

from .auth import auth_router
from .ingestion import ingestion_router
from .library import library_router
from .platform.config import settings


def build_api_router() -> APIRouter:
    """Assemble the versioned API from every domain module."""
    router = APIRouter(prefix=settings.api_prefix)
    router.include_router(auth_router)
    router.include_router(library_router)
    router.include_router(ingestion_router)
    return router
