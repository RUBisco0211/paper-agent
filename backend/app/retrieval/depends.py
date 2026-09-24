from typing import Annotated

from fastapi import Depends

from ..embedding import build_embedding_adapter
from ..library.repo import PaperRepository
from ..platform.config import settings
from ..platform.database import SessionDep
from ..projects.repo import ProjectRepository
from .ports import EmbeddingAdapter
from .repo import ChunkRepository
from .service import SearchService


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
    )


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
