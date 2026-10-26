"""Ports the library module needs from other domains.

Kept as protocols so the library never imports the pipelines implementation at
module scope; wiring happens in ``library.depends``.
"""

from typing import Protocol
from uuid import UUID

from ..pipelines.domain import Run


class MetadataEnricherPort(Protocol):
    """Fill a paper's bibliographic facts from its stored source file."""

    def submit(self, paper_id: UUID, identifiers: tuple = ()) -> None: ...


class RunStarter(Protocol):
    """Join a user to a paper's processing, starting one when there is none."""

    def request(self, *, user_id: UUID, paper_id: UUID) -> Run: ...

    def latest_for_papers(self, paper_ids: list[UUID]) -> dict[UUID, Run]:
        """The most recent run of each paper, whichever user asked for it."""
        ...
