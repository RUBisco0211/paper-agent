from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import Base, CreatedAtMixin


class SessionBindingRecord(Base, CreatedAtMixin):
    """Business-owned scope for an AgentScope session in the separate database."""

    __tablename__ = "session_bindings"

    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )


class BoundCitationRecord(Base, CreatedAtMixin):
    """Evidence registered for an AgentScope session."""

    __tablename__ = "session_bound_citations"

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("session_bindings.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    citation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    title_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SessionBindingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, session_id: UUID) -> SessionBindingRecord | None:
        return self._session.get(SessionBindingRecord, session_id)

    def has_project_sessions(self, *, user_id: UUID, project_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(SessionBindingRecord.session_id)
                .where(
                    SessionBindingRecord.user_id == user_id,
                    SessionBindingRecord.project_id == project_id,
                )
                .limit(1)
            )
            is not None
        )

    def list_for_user(
        self, *, user_id: UUID, limit: int, offset: int
    ) -> tuple[list[SessionBindingRecord], int]:
        statement = select(SessionBindingRecord).where(
            SessionBindingRecord.user_id == user_id
        )
        total = (
            self._session.scalar(
                statement.with_only_columns(func.count(SessionBindingRecord.session_id))
            )
            or 0
        )
        records = self._session.scalars(
            statement.order_by(
                SessionBindingRecord.created_at.desc(),
                SessionBindingRecord.session_id,
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return list(records), int(total)

    def add(
        self, *, session_id: UUID, user_id: UUID, project_id: UUID | None
    ) -> SessionBindingRecord:
        record = SessionBindingRecord(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def commit(self) -> None:
        self._session.commit()

    def delete(self, record: SessionBindingRecord) -> None:
        self._session.delete(record)

    def get_citation(
        self, session_id: UUID, citation_id: str
    ) -> BoundCitationRecord | None:
        return self._session.get(BoundCitationRecord, (session_id, citation_id))

    def add_citation(
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
    ) -> None:
        self._session.execute(
            pg_insert(BoundCitationRecord)
            .values(
                session_id=session_id,
                citation_id=citation_id,
                user_paper_id=user_paper_id,
                chunk_ids=[str(chunk_id) for chunk_id in chunk_ids],
                title_path=title_path,
                snippet=snippet,
                page_start=page_start,
                page_end=page_end,
            )
            .on_conflict_do_nothing(
                index_elements=["session_id", "citation_id"],
            ),
        )
