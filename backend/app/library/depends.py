from typing import Annotated

from fastapi import Depends

from app.literature_support.scholar.metadata import (
    MetadataResolver,
    build_default_resolver,
)
from app.literature_support.scholar.pdf_fetch import PdfFetcher

from ..platform.config import settings
from ..platform.database import SessionDep, SessionFactoryDep
from ..platform.storage import StorageDep
from ..platform.tasks import TaskSchedulerDep
from .ports import ImportStarter, MetadataEnricherPort
from .repo import PaperRepository
from .service import PaperLibraryService


def get_paper_repository(session: SessionDep) -> PaperRepository:
    return PaperRepository(session)


PaperRepositoryDep = Annotated[PaperRepository, Depends(get_paper_repository)]


def get_import_starter(
    session: SessionDep,
    storage: StorageDep,
    session_factory: SessionFactoryDep,
    scheduler: TaskSchedulerDep,
) -> ImportStarter:
    """Build the shared import workflow for this request."""
    from app.literature_support.importing.pipeline import build_import_service

    return build_import_service(
        session=session,
        storage=storage,
        session_factory=session_factory,
        scheduler=scheduler,
    )


ImportStarterDep = Annotated[ImportStarter, Depends(get_import_starter)]


def get_metadata_resolver() -> MetadataResolver:
    """Exact identifier lookup (Crossref for DOIs, arXiv for arXiv ids)."""
    return build_default_resolver()


MetadataResolverDep = Annotated[MetadataResolver, Depends(get_metadata_resolver)]


def get_pdf_fetcher() -> PdfFetcher:
    return PdfFetcher(max_bytes=settings.max_pdf_bytes)


PdfFetcherDep = Annotated[PdfFetcher, Depends(get_pdf_fetcher)]


def get_metadata_enricher(
    storage: StorageDep,
    resolver: MetadataResolverDep,
    session_factory: SessionFactoryDep,
) -> MetadataEnricherPort:
    from app.literature_support.scholar.enrichment import MetadataEnricher

    return MetadataEnricher(
        storage=storage,
        resolver=resolver,
        session_factory=session_factory,
    )


MetadataEnricherDep = Annotated[MetadataEnricherPort, Depends(get_metadata_enricher)]


def get_paper_library_service(
    papers: PaperRepositoryDep,
    imports: ImportStarterDep,
    enrichment: MetadataEnricherDep,
    storage: StorageDep,
) -> PaperLibraryService:
    return PaperLibraryService(papers, imports, enrichment, storage)


PaperLibraryServiceDep = Annotated[
    PaperLibraryService,
    Depends(get_paper_library_service),
]
