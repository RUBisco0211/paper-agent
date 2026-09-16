from typing import Annotated

from fastapi import Depends

from ..library.persistence import PaperRepository
from ..platform.config import settings
from ..platform.database import SessionDep
from ..projects.persistence import ProjectRepository
from .application import SearchService
from .embedding import EmbeddingClient
from .persistence import ChunkRepository


def get_chunk_repository(session: SessionDep) -> ChunkRepository:
    return ChunkRepository(session)


ChunkRepositoryDep = Annotated[ChunkRepository, Depends(get_chunk_repository)]


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_embedding_client() -> EmbeddingClient:
    """Instance-level embedding model; user input never selects it."""
    return EmbeddingClient()


EmbeddingClientDep = Annotated[EmbeddingClient, Depends(get_embedding_client)]


def get_search_service(
    chunks: ChunkRepositoryDep,
    session: SessionDep,
    projects: ProjectRepositoryDep,
    embeddings: EmbeddingClientDep,
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
