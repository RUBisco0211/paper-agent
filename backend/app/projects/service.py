from uuid import UUID

import structlog

from ..library.service import LibraryEntry, PaperLibraryService
from ..platform.errors import ConflictError, ErrorCode, NotFoundError
from .domain import Project, normalize_name
from .ports import ProjectSessionGuard
from .repo import ProjectRepository

logger = structlog.get_logger(__name__)


class ProjectPapers:
    """A project together with the result of adding papers to it."""

    def __init__(
        self,
        added: list[LibraryEntry],
        already_present: list[UUID],
    ) -> None:
        self.added = added
        self.already_present = already_present


class ProjectService:
    """Use cases for projects and their paper scope."""

    def __init__(
        self,
        repository: ProjectRepository,
        library: PaperLibraryService,
        session_guard: ProjectSessionGuard,
    ) -> None:
        self._repository = repository
        self._library = library
        self._session_guard = session_guard

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None = None,
    ) -> Project:
        project = self._repository.add_project(
            user_id=user_id,
            name=normalize_name(name),
            description=(description or "").strip() or None,
        )
        self._repository.commit()
        logger.info("service.project.created", project_id=str(project.id))
        return project

    def list_projects(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Project, int]], int]:
        projects, total = self._repository.list_projects(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        counts = self._repository.count_papers([project.id for project in projects])
        return [(project, counts.get(project.id, 0)) for project in projects], total

    def get(self, *, user_id: UUID, project_id: UUID) -> Project:
        project = self._repository.get_project(project_id)
        if project is None or project.user_id != user_id:
            raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)
        return project

    def paper_count(self, project_id: UUID) -> int:
        return self._repository.count_papers([project_id]).get(project_id, 0)

    def rename(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        name: str | None = None,
        description: str | None = None,
        clear_description: bool = False,
    ) -> Project:
        self.get(user_id=user_id, project_id=project_id)
        updated = self._repository.update_project(
            project_id,
            name=normalize_name(name) if name is not None else None,
            description=description,
            clear_description=clear_description,
        )
        assert updated is not None
        self._repository.commit()
        logger.info("service.project.updated", project_id=str(project_id))
        return updated

    def delete(self, *, user_id: UUID, project_id: UUID) -> None:
        """Delete a project after its AgentScope sessions have been removed.

        Personal library entries and the shared PDF facts are untouched.
        """
        self.get(user_id=user_id, project_id=project_id)
        if self._session_guard.has_project_sessions(
            user_id=user_id, project_id=project_id
        ):
            raise ConflictError("请先删除项目会话", code=ErrorCode.CONFLICT)
        self._repository.delete_project(project_id)
        self._repository.commit()
        logger.info(
            "service.project.deleted",
            project_id=str(project_id),
        )

    def add_papers(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        user_paper_ids: list[UUID],
    ) -> ProjectPapers:
        self.get(user_id=user_id, project_id=project_id)
        owned = {
            entry.user_paper.id
            for entry in self._library.entries_for(
                user_id=user_id,
                user_paper_ids=user_paper_ids,
            )
        }
        missing = [item for item in user_paper_ids if item not in owned]
        if missing:
            raise NotFoundError(
                "论文不存在",
                code=ErrorCode.PAPER_NOT_FOUND,
                details={"paper_ids": [str(item) for item in missing]},
            )

        added, skipped = self._repository.add_papers(
            project_id=project_id,
            user_paper_ids=user_paper_ids,
        )
        self._repository.commit()
        entries = self._library.entries_for(
            user_id=user_id,
            user_paper_ids=[paper.user_paper_id for paper in added],
        )
        logger.info(
            "service.project.papers_added",
            project_id=str(project_id),
            added=len(entries),
            already_present=len(skipped),
        )
        return ProjectPapers(added=entries, already_present=skipped)

    def list_papers(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[LibraryEntry], int]:
        self.get(user_id=user_id, project_id=project_id)
        links, total = self._repository.papers_of(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
        entries = self._library.entries_for(
            user_id=user_id,
            user_paper_ids=[link.user_paper_id for link in links],
        )
        return entries, total

    def paper_ids(self, *, user_id: UUID, project_id: UUID) -> set[UUID]:
        """Authorized paper scope of a project session."""
        self.get(user_id=user_id, project_id=project_id)
        return self._repository.paper_ids_of(project_id)
