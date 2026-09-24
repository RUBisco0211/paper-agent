"""Execution interface for queued ingestion jobs."""

from typing import Protocol
from uuid import UUID


class IngestionJobRunner(Protocol):
    """Executes a queued job outside the request scope."""

    def submit(self, job_id: UUID) -> None: ...
