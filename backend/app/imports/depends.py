from typing import Annotated

from fastapi import Depends

from app.literature_support.scholar.pdf_sources import DoiPdfLocator

from ..platform.database import SessionFactoryDep
from ..platform.discovery import DiscoveryAggregator
from ..platform.storage import StorageDep
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


def get_import_service(
    session_factory: SessionFactoryDep,
    storage: StorageDep,
) -> ImportService:
    """Queue identifier downloads, or reuse a paper whose file is already here.

    The runs service is built from the same factory so a reused paper joins its
    run without going through the download worker.
    """
    from app.pipelines.runs import RunService

    return ImportService(
        session_factory=session_factory,
        storage=storage,
        runs=RunService(session_factory=session_factory),
    )


ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]


def get_import_approval_service(
    session_factory: SessionFactoryDep, importer: ImportServiceDep
) -> ImportApprovalService:
    return ImportApprovalService(session_factory, importer)


ImportApprovalServiceDep = Annotated[
    ImportApprovalService, Depends(get_import_approval_service)
]
