"""Ports the library module needs from other domains.

Kept as a protocol so the library never imports the import workflow
implementation at module scope; wiring happens in ``library.depends``.
"""

from typing import Protocol
from uuid import UUID

from app.imports.domain import PaperImport

from .domain import Paper


class MetadataEnricherPort(Protocol):
    """Fill a paper's bibliographic facts from its stored source file."""

    def submit(self, paper_id: UUID, identifiers: tuple = ()) -> None: ...


class ImportStarter(Protocol):
    """Start and inspect the import that brings a paper into the library.

    An import finishes on its own; the library only records that a paper exists
    and links the requesting user to it once the import is ready.
    """

    def start_for_paper(
        self,
        paper: Paper,
        *,
        initiated_by: UUID,
        identifier_type: str,
        identifier: str,
    ) -> PaperImport: ...

    def get(self, import_id: UUID) -> PaperImport | None: ...

    def retry(self, import_id: UUID) -> PaperImport: ...

    def latest_imports_for_papers(
        self,
        paper_ids: list[UUID],
    ) -> dict[UUID, PaperImport]: ...
