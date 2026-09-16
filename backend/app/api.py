"""Cross-domain HTTP wiring: root router and shared response models."""

from fastapi import APIRouter

from .platform.config import settings


def build_api_router() -> APIRouter:
    """Assemble the versioned API from every domain module."""
    router = APIRouter(prefix=settings.api_prefix)
    return router
