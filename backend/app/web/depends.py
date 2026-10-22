from typing import Annotated

from fastapi import Depends

from ..platform.config import settings
from ..platform.database import SessionDep
from ..platform.redis import get_redis
from ..service_credentials.depends import CredentialCipherDep
from ..service_credentials.repo import ServiceCredentialRepository
from ..service_credentials.service import ServiceCredentialService
from .ports import TavilyWeb
from .repo import WebPageCache
from .service import WebSearchService


def build_web_search_service(
    session: SessionDep,
    cipher: CredentialCipherDep,
) -> WebSearchService:
    """Wire the provider and the cache around the shared per-user credential store."""
    return WebSearchService(
        ServiceCredentialService(ServiceCredentialRepository(session), cipher),
        WebPageCache(get_redis()),
        lambda api_key: TavilyWeb(
            api_key=api_key,
            base_url=settings.web_search_base_url,
            timeout_seconds=settings.web_search_timeout_seconds,
        ),
    )


WebSearchServiceDep = Annotated[WebSearchService, Depends(build_web_search_service)]
