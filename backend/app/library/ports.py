"""Ports the library module needs from other domains.

Kept as a protocol so the library never imports the ingestion implementation at
module scope; wiring happens in ``library.depends``.
"""

from typing import Protocol
from uuid import UUID

from ..ingestion.domain import IngestionJob


class IngestionStarter(Protocol):
    def start_for_paper(self, paper_id: UUID) -> IngestionJob | None: ...

    def get_job(self, job_id: UUID) -> IngestionJob | None: ...

    def retry_job(self, job_id: UUID) -> IngestionJob: ...

    def active_job_for_paper(self, paper_id: UUID) -> IngestionJob | None: ...

    def latest_jobs_for_papers(
        self,
        paper_ids: list[UUID],
    ) -> dict[UUID, IngestionJob]: ...
