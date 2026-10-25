"""Ports the import module needs from its environment."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from ..library.ports import ImportStarter
from ..platform.database import SessionFactory
from ..platform.storage import ObjectStorage
from ..platform.tasks import TaskScheduler


class SourceAcquirer(Protocol):
    """Gets the source file for an import and records its paper.

    Runs inside the worker, not the request, so a slow download never holds an
    HTTP connection; returns ``None`` when no file could be found.
    """

    def acquire(self, import_id: UUID) -> UUID | None: ...


class ImportRunner(Protocol):
    """Runs an import's stages.

    ``submit`` runs the whole flow (used after a retry); ``submit_stages`` runs
    only what is still pending, which is what an import needs once its source
    file is stored.
    """

    def submit(self, import_id: UUID) -> None: ...

    def submit_stages(self, import_id: UUID) -> None: ...


class ImportStarterFactory(Protocol):
    def __call__(
        self,
        *,
        session: Session,
        storage: ObjectStorage,
        session_factory: SessionFactory,
        scheduler: TaskScheduler,
    ) -> ImportStarter: ...


class PdfSourceLocator(Protocol):
    def find(self, doi: str) -> list[str]: ...


class PaperDiscoveryAdapter(Protocol):
    def search(self, query: str, limit: int) -> "PaperDiscoveryResult": ...


class PaperDiscoveryResult(Protocol):
    papers: list[dict]
    failed_sources: list[str]
