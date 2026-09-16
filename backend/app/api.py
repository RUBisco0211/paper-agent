"""Cross-domain HTTP wiring: root router and shared response models."""

from fastapi import APIRouter

from .auth import auth_router
from .platform.config import settings


def build_api_router() -> APIRouter:
    """Assemble the versioned API from every domain module."""
    router = APIRouter(prefix=settings.api_prefix)
    router.include_router(auth_router)
    return router
