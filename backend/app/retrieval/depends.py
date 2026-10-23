from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.literature_support.embedding import build_embedding_adapter

from ..library.depends import PaperLibraryServiceDep
from ..library.repo import PaperRepository
from ..platform.config import settings
from ..platform.database import SessionDep
from ..projects.repo import ProjectRepository
from ..service_credentials.depends import CredentialCipherDep
from ..service_credentials.repo import ServiceCredentialRepository
from ..service_credentials.service import ServiceCredentialService
from ..sessions.depends import SessionBindingServiceDep
from .ports import EmbeddingAdapter
from .repo import ChunkRepository
from .service import (
    BoundPaperService,
    BoundSearchService,
    SearchEmbeddingFactory,
    SearchService,
)


def get_chunk_repository(session: SessionDep) -> ChunkRepository:
    return ChunkRepository(session)


ChunkRepositoryDep = Annotated[ChunkRepository, Depends(get_chunk_repository)]


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


ProjectRepositoryDep = Annotated[ProjectRepository, Depends(get_project_repository)]


def _build_adapter(api_key: str) -> EmbeddingAdapter:
    """Indirection so tests can substitute the provider call."""
    return build_embedding_adapter(api_key=api_key)


def get_search_embedding_factory(
    session: SessionDep,
    cipher: CredentialCipherDep,
) -> SearchEmbeddingFactory:
    """Read the searching user's own key; the model stays deployment-wide."""

    def factory(user_id: UUID) -> EmbeddingAdapter | None:
        service = ServiceCredentialService(ServiceCredentialRepository(session), cipher)
        api_key = service.secret(user_id, "embedding", "api_key")
        if api_key is None:
            return None
        return _build_adapter(api_key)

    return factory


SearchEmbeddingFactoryDep = Annotated[
    SearchEmbeddingFactory, Depends(get_search_embedding_factory)
]


def get_search_service(
    chunks: ChunkRepositoryDep,
    session: SessionDep,
    projects: ProjectRepositoryDep,
    embeddings: SearchEmbeddingFactoryDep,
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
