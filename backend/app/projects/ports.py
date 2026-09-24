from typing import Protocol
from uuid import UUID


class ProjectSessionCleaner(Protocol):
    """Terminates and purges the sessions bound to a deleted project.

    Implemented by the sessions module; the projects module only declares the
    boundary so deleting a project stays a single user-visible operation.
    """

    def purge_project_sessions(self, *, user_id: UUID, project_id: UUID) -> int: ...
