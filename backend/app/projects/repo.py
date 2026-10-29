from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..library.repo import PaperRecord, UserPaperRecord
from ..platform.database import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from .domain import Project, ProjectPaper


class ProjectRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "projects"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectPaperRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "project_papers"
    __table_args__ = (
        UniqueConstraint("project_id", "user_paper_id", name="uq_project_paper"),
    )

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProjectRepository:
    """Persistence for projects and their paper sets."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # Projects --------------------------------------------------------------
    def add_project(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
    ) -> Project:
        record = ProjectRecord(user_id=user_id, name=name, description=description)
        self._session.add(record)
        self._session.flush()
        return _to_project(record)

    def get_project(self, project_id: UUID) -> Project | None:
        record = self._session.get(ProjectRecord, project_id)
        return _to_project(record) if record else None

    def list_projects(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[Project], int]:
        statement = select(ProjectRecord).where(ProjectRecord.user_id == user_id)
        count_statement = statement.with_only_columns(func.count(ProjectRecord.id))
        records = self._session.scalars(
            statement.order_by(ProjectRecord.created_at, ProjectRecord.id)
            .limit(limit)
            .offset(offset),
        ).all()
        total = self._session.scalar(count_statement) or 0
        return [_to_project(record) for record in records], int(total)

    def update_project(
        self,
        project_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        clear_description: bool = False,
    ) -> Project | None:
        record = self._session.get(ProjectRecord, project_id)
        if record is None:
            return None
        if name is not None:
            record.name = name
        if clear_description:
            record.description = None
        elif description is not None:
            record.description = description
        self._session.flush()
        return _to_project(record)

    def delete_project(self, project_id: UUID) -> None:
        record = self._session.get(ProjectRecord, project_id)
        if record is not None:
            self._session.delete(record)
            self._session.flush()

    def count_papers(self, project_ids: list[UUID]) -> dict[UUID, int]:
        if not project_ids:
            return {}
        rows = self._session.execute(
            select(
                ProjectPaperRecord.project_id,
                func.count(ProjectPaperRecord.id),
            )
            .where(ProjectPaperRecord.project_id.in_(project_ids))
            .group_by(ProjectPaperRecord.project_id),
        ).all()
        return {project_id: int(count) for project_id, count in rows}

    # Project papers --------------------------------------------------------
    def add_papers(
        self,
        *,
        project_id: UUID,
        user_paper_ids: list[UUID],
    ) -> tuple[list[ProjectPaper], list[UUID]]:
        existing = self.paper_ids_of(project_id)
        next_position = len(existing)
        added: list[ProjectPaper] = []
        skipped: list[UUID] = []
        for user_paper_id in user_paper_ids:
            if user_paper_id in existing:
                skipped.append(user_paper_id)
                continue
            next_position += 1
            record = ProjectPaperRecord(
                project_id=project_id,
                user_paper_id=user_paper_id,
                position=next_position,
            )
            self._session.add(record)
            self._session.flush()
            existing.add(user_paper_id)
            added.append(_to_project_paper(record))
        return added, skipped

    def paper_ids_of(self, project_id: UUID) -> set[UUID]:
        return set(
            self._session.scalars(
                select(ProjectPaperRecord.user_paper_id).where(
                    ProjectPaperRecord.project_id == project_id,
                ),
            ).all(),
        )

    def papers_of(
        self,
        *,
        project_id: UUID,
        limit: int,
        offset: int,
        user_id: UUID,
        query: str | None = None,
    ) -> tuple[list[ProjectPaper], int]:
        visible_papers = (
            select(UserPaperRecord.id)
            .join(PaperRecord, PaperRecord.id == UserPaperRecord.paper_id)
            .where(UserPaperRecord.user_id == user_id)
        )
        if query:
            # Bibliographic facts live on the shared paper, not the entry.
            visible_papers = visible_papers.where(
                PaperRecord.bibliographic["title"].astext.ilike(f"%{query.strip()}%"),
            )
        statement = select(ProjectPaperRecord).where(
            ProjectPaperRecord.project_id == project_id,
            ProjectPaperRecord.user_paper_id.in_(visible_papers),
        )
        count_statement = statement.with_only_columns(func.count(ProjectPaperRecord.id))
        records = self._session.scalars(
            statement.order_by(
                ProjectPaperRecord.position,
                ProjectPaperRecord.added_at,
            )
            .limit(limit)
            .offset(offset),
        ).all()
        total = self._session.scalar(count_statement) or 0
        return [_to_project_paper(record) for record in records], int(total)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def _to_project(record: ProjectRecord) -> Project:
    return Project(
        id=record.id,
        user_id=record.user_id,
        name=record.name,
        description=record.description,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_project_paper(record: ProjectPaperRecord) -> ProjectPaper:
    return ProjectPaper(
        id=record.id,
        project_id=record.project_id,
        user_paper_id=record.user_paper_id,
        position=record.position,
        added_at=record.added_at,
    )
