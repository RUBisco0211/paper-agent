from typing import Annotated

from fastapi import Depends

from app.literature_support.scholar.pdf_sources import DoiPdfLocator

from ..library.depends import MetadataResolverDep, PdfFetcherDep
from ..platform.database import SessionDep, SessionFactoryDep
from ..platform.discovery import DiscoveryAggregator
from ..platform.storage import StorageDep
from ..platform.tasks import TaskSchedulerDep
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
    session: SessionDep,
    storage: StorageDep,
    session_factory: SessionFactoryDep,
    scheduler: TaskSchedulerDep,
    resolver: MetadataResolverDep,
    pdf_fetcher: PdfFetcherDep,
    pdf_locator: PdfSourceLocatorDep,
) -> ImportService:
    """Wire identifier imports to the shared processing factory."""
    from app.literature_support.processing.pipeline import build_ingestion_service

    return ImportService(
        session_factory=session_factory,
        storage=storage,
        resolver=resolver,
        pdf_fetcher=pdf_fetcher,
        pdf_locator=pdf_locator,
        scheduler=scheduler,
        ingestion_starter_factory=build_ingestion_service,
    )


ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]


def get_import_approval_service(
    session_factory: SessionFactoryDep, importer: ImportServiceDep
) -> ImportApprovalService:
    return ImportApprovalService(session_factory, importer)


ImportApprovalServiceDep = Annotated[
    ImportApprovalService, Depends(get_import_approval_service)
]
