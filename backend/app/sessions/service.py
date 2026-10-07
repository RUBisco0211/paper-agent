from uuid import UUID

from ..platform.errors import ConflictError, ErrorCode, NotFoundError
from ..projects.repo import ProjectRepository
from .repo import SessionBindingRecord, SessionBindingRepository


class SessionBindingService:
    def __init__(
        self,
        bindings: SessionBindingRepository,
        projects: ProjectRepository,
    ) -> None:
        self._bindings = bindings
        self._projects = projects

    def create(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        project_id: UUID | None,
    ) -> SessionBindingRecord:
        if project_id is not None:
            project = self._projects.get_project(project_id)
            if project is None or project.user_id != user_id:
                raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)
        if self._bindings.get(session_id) is not None:
            raise ConflictError("会话范围已绑定", code=ErrorCode.CONFLICT)
        record = self._bindings.add(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
        )
        self._bindings.commit()
        return record

    def require(self, *, session_id: UUID, user_id: UUID) -> SessionBindingRecord:
        record = self._bindings.get(session_id)
        if record is None or record.user_id != user_id:
            raise NotFoundError("会话不存在", code=ErrorCode.SESSION_NOT_FOUND)
        return record

    def list_for_user(
        self, *, user_id: UUID, limit: int, offset: int
    ) -> tuple[list[SessionBindingRecord], int]:
        return self._bindings.list_for_user(user_id=user_id, limit=limit, offset=offset)

    def delete(self, *, session_id: UUID, user_id: UUID) -> None:
        record = self.require(session_id=session_id, user_id=user_id)
        self._bindings.delete(record)
        self._bindings.commit()

    def record_citation(
        self,
        *,
        session_id: UUID,
        citation_id: str,
        user_paper_id: UUID,
        chunk_ids: list[UUID],
        title_path: str | None,
        snippet: str,
        page_start: int | None,
        page_end: int | None,
        source_locations: list[dict] | None = None,
    ) -> None:
        self._bindings.add_citation(
            session_id=session_id,
            citation_id=citation_id,
            user_paper_id=user_paper_id,
            chunk_ids=chunk_ids,
            title_path=title_path,
            snippet=snippet,
            page_start=page_start,
            page_end=page_end,
            source_locations=source_locations,
        )
        self._bindings.commit()

    def require_citation(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        citation_id: str,
    ):
        self.require(session_id=session_id, user_id=user_id)
        citation = self._bindings.get_citation(session_id, citation_id)
        if citation is None:
            raise NotFoundError("引用不存在", code=ErrorCode.CITATION_NOT_FOUND)
        return citation
