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
from .ports import MetadataEnricherPort, RunStarter
from .repo import PaperRepository
from .service import PaperLibraryService


def get_paper_repository(session: SessionDep) -> PaperRepository:
    return PaperRepository(session)


PaperRepositoryDep = Annotated[PaperRepository, Depends(get_paper_repository)]


def get_run_starter(session_factory: SessionFactoryDep) -> RunStarter:
    """Join a user to a paper's processing; no download or parse happens here."""
    from app.pipelines.runs import RunService

    return RunService(session_factory=session_factory)


RunStarterDep = Annotated[RunStarter, Depends(get_run_starter)]


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
    runs: RunStarterDep,
    enrichment: MetadataEnricherDep,
    storage: StorageDep,
) -> PaperLibraryService:
    return PaperLibraryService(
        papers,
        runs,
        enrichment,
        storage,
        page_max_chars=settings.paper_page_max_chars,
        image_max_bytes=settings.paper_image_max_bytes,
    )


PaperLibraryServiceDep = Annotated[
    PaperLibraryService,
    Depends(get_paper_library_service),
]
