from typing import Annotated

from fastapi import Depends

from ..platform.config import settings
from ..platform.database import SessionDep
from ..platform.storage import StorageDep
from ..scholar.metadata import MetadataResolver, build_default_resolver
from ..scholar.pdf_fetch import PdfFetcher
from .application import PaperLibraryService
from .persistence import PaperRepository
from .ports import IngestionStarter


def get_paper_repository(session: SessionDep) -> PaperRepository:
    return PaperRepository(session)


PaperRepositoryDep = Annotated[PaperRepository, Depends(get_paper_repository)]


def get_ingestion_starter(session: SessionDep) -> IngestionStarter:
    """Build the ingestion service without creating an import cycle.

    The import is intentionally local: the ingestion module depends on library
    persistence, so a module-level import here would close the loop.
    """
    from ..ingestion.application import IngestionService
    from ..ingestion.persistence import IngestionRepository

    return IngestionService(IngestionRepository(session), PaperRepository(session))


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
