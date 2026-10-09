"""Ingestion factory used when imported metadata gains a PDF."""

from typing import Protocol

from sqlalchemy.orm import Session

from ..library.ports import IngestionStarter
from ..platform.database import SessionFactory
from ..platform.storage import ObjectStorage
from ..platform.tasks import TaskScheduler


class IngestionStarterFactory(Protocol):
    def __call__(
        self,
        *,
        session: Session,
        storage: ObjectStorage,
        session_factory: SessionFactory,
        scheduler: TaskScheduler,
    ) -> IngestionStarter: ...


class PdfSourceLocator(Protocol):
    def find(self, doi: str) -> list[str]: ...
