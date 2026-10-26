"""Domain of the import entry points: request a download, approve a batch.

The processing itself lives in ``app.pipelines``; this module only owns what a
user asks for and the discovery results they were shown before asking.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """A queued request to turn an identifier into a stored file."""

    id: UUID
    user_id: UUID
    identifier_type: str
    identifier: str
    status: str
    created_at: datetime
