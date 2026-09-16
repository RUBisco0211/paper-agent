"""Projects: a named subset of one user's personal library."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..platform.errors import DomainValidationError

NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 2000


class InvalidProjectName(DomainValidationError):
    """Raised when a project name violates the domain invariant."""


def normalize_name(name: str) -> str:
    normalized = " ".join((name or "").split())
    if not normalized:
        raise InvalidProjectName("项目名称不能为空")
    if len(normalized) > NAME_MAX_LENGTH:
        raise InvalidProjectName(f"项目名称不能超过 {NAME_MAX_LENGTH} 个字符")
    return normalized


@dataclass(frozen=True, slots=True)
class Project:
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectPaper:
    id: UUID
    project_id: UUID
    user_paper_id: UUID
    position: int
    added_at: datetime
