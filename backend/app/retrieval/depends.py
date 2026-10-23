from typing import Annotated

from fastapi import Depends

from app.literature_support.embedding import build_embedding_adapter

from ..library.depends import PaperLibraryServiceDep
from ..library.repo import PaperRepository
from ..platform.config import settings
from ..platform.database import SessionDep
from ..projects.repo import ProjectRepository
from ..sessions.depends import SessionBindingServiceDep
from .ports import EmbeddingAdapter
from .repo import ChunkRepository
from .service import (
    BoundPaperService,
    BoundSearchService,
    SearchService,
)


def get_chunk_repository(session: SessionDep) -> ChunkRepository:
    return ChunkRepository(session)


ChunkRepositoryDep = Annotated[ChunkRepository, Depends(get_chunk_repository)]


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_embedding_adapter() -> EmbeddingAdapter:
    """Instance-level embedding model; user input never selects it."""
    return build_embedding_adapter()


EmbeddingAdapterDep = Annotated[EmbeddingAdapter, Depends(get_embedding_adapter)]


def get_search_service(
    chunks: ChunkRepositoryDep,
    session: SessionDep,
    projects: ProjectRepositoryDep,
    embeddings: EmbeddingAdapterDep,
) -> SearchService:
    return SearchService(
        chunks,
        PaperRepository(session),
        projects,
        embeddings,
        keyword_top_n=settings.keyword_top_n,
        vector_top_n=settings.vector_top_n,
        rrf_k=settings.rrf_k,
        max_evidence=settings.max_evidence_chunks,
        max_evidence_per_paper=settings.max_evidence_per_paper,
        evidence_max_chars=settings.evidence_max_chars,
    )


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


def get_bound_search_service(
    bindings: SessionBindingServiceDep,
    search: SearchServiceDep,
) -> BoundSearchService:
    return BoundSearchService(bindings, search)


BoundSearchServiceDep = Annotated[BoundSearchService, Depends(get_bound_search_service)]


def get_bound_paper_service(
    bindings: SessionBindingServiceDep,
    library: PaperLibraryServiceDep,
    projects: ProjectRepositoryDep,
) -> BoundPaperService:
    return BoundPaperService(bindings, library, projects)


BoundPaperServiceDep = Annotated[BoundPaperService, Depends(get_bound_paper_service)]
