from typing import Annotated

from fastapi import Depends

from app.literature_support.scholar.pdf_sources import DoiPdfLocator

from ..platform.database import SessionFactoryDep
from ..platform.discovery import DiscoveryAggregator
from ..sessions.depends import SessionBindingServiceDep
from .ports import PdfSourceLocator
from .service import DiscoveryService, ImportApprovalService, ImportService


def get_discovery_adapter() -> DiscoveryAggregator:
    return DiscoveryAggregator()


DiscoveryAdapterDep = Annotated[DiscoveryAggregator, Depends(get_discovery_adapter)]


def get_discovery_service(
    bindings: SessionBindingServiceDep, provider: DiscoveryAdapterDep
) -> DiscoveryService:
    return DiscoveryService(bindings, provider)


DiscoveryServiceDep = Annotated[DiscoveryService, Depends(get_discovery_service)]


def get_pdf_locator() -> PdfSourceLocator:
    return DoiPdfLocator()


PdfSourceLocatorDep = Annotated[PdfSourceLocator, Depends(get_pdf_locator)]


def get_import_service(session_factory: SessionFactoryDep) -> ImportService:
    """Queue identifier downloads; the worker fetches and processes them."""
    return ImportService(session_factory=session_factory)


ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]


def get_import_approval_service(
    session_factory: SessionFactoryDep, importer: ImportServiceDep
) -> ImportApprovalService:
    return ImportApprovalService(session_factory, importer)


ImportApprovalServiceDep = Annotated[
    ImportApprovalService, Depends(get_import_approval_service)
]
