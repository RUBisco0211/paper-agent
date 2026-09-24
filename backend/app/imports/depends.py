from typing import Annotated

from fastapi import Depends

from ..library.depends import MetadataResolverDep, PdfFetcherDep
from ..platform.database import SessionDep, SessionFactoryDep
from ..platform.storage import StorageDep
from ..platform.tasks import TaskSchedulerDep
from .service import ImportService


def get_import_service(
    session: SessionDep,
    storage: StorageDep,
    session_factory: SessionFactoryDep,
    scheduler: TaskSchedulerDep,
    resolver: MetadataResolverDep,
    pdf_fetcher: PdfFetcherDep,
) -> ImportService:
    """Wire identifier imports to the shared processing factory."""
    from ..processing.service import build_ingestion_service

    return ImportService(
        session_factory=session_factory,
        storage=storage,
        resolver=resolver,
        pdf_fetcher=pdf_fetcher,
        scheduler=scheduler,
        ingestion_starter_factory=build_ingestion_service,
    )


ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]
