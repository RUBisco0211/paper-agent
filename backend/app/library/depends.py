from typing import Annotated

from fastapi import Depends

from ..platform.config import settings
from ..platform.database import SessionDep, SessionFactoryDep
from ..platform.storage import StorageDep
from ..platform.tasks import TaskSchedulerDep
from ..scholar.metadata import MetadataResolver, build_default_resolver
from ..scholar.pdf_fetch import PdfFetcher
from .ports import IngestionStarter
from .repo import PaperRepository
from .service import PaperLibraryService


def get_paper_repository(session: SessionDep) -> PaperRepository:
    return PaperRepository(session)


PaperRepositoryDep = Annotated[PaperRepository, Depends(get_paper_repository)]


def get_ingestion_starter(
    session: SessionDep,
    storage: StorageDep,
    session_factory: SessionFactoryDep,
    scheduler: TaskSchedulerDep,
) -> IngestionStarter:
    """Build the shared ingestion service for this request.
    """
    from ..processing.service import build_ingestion_service

    return build_ingestion_service(
        session=session,
        storage=storage,
        session_factory=session_factory,
        scheduler=scheduler,
    )


IngestionStarterDep = Annotated[IngestionStarter, Depends(get_ingestion_starter)]


def get_metadata_resolver() -> MetadataResolver:
    """Exact identifier lookup (Crossref for DOIs, arXiv for arXiv ids)."""
    return build_default_resolver()


MetadataResolverDep = Annotated[MetadataResolver, Depends(get_metadata_resolver)]


def get_pdf_fetcher() -> PdfFetcher:
    return PdfFetcher(max_bytes=settings.max_pdf_bytes)


PdfFetcherDep = Annotated[PdfFetcher, Depends(get_pdf_fetcher)]


def get_paper_library_service(
    papers: PaperRepositoryDep,
    ingestion: IngestionStarterDep,
    storage: StorageDep,
    resolver: MetadataResolverDep,
    pdf_fetcher: PdfFetcherDep,
) -> PaperLibraryService:
    return PaperLibraryService(papers, ingestion, storage, resolver, pdf_fetcher)


PaperLibraryServiceDep = Annotated[
    PaperLibraryService,
    Depends(get_paper_library_service),
]
