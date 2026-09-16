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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from .domain import Citation, Delivery, PendingMessage
from .domain import Session as SessionEntity


class SessionRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Conversation boundary; ``project_id`` fixes its retrieval scope."""

    __tablename__ = "sessions"

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
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PendingMessageRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Accepted user input that has not been delivered to the agent yet."""

    __tablename__ = "session_pending_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "delivery", "position", name="uq_pending_order"),
    )

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delivery: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class CitationRecord(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Evidence a stored answer may point at; resolved per session and user."""

    __tablename__ = "session_citations"
    __table_args__ = (
        UniqueConstraint("session_id", "citation_id", name="uq_session_citation"),
    )

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    citation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    title_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SessionRepository:
    """Persistence for sessions, pending input and stored citations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # Sessions --------------------------------------------------------------
    def add_session(
        self,
        *,
        user_id: UUID,
        project_id: UUID | None,
        title: str | None,
    ) -> SessionEntity:
        record = SessionRecord(
            user_id=user_id,
            project_id=project_id,
            title=title,
        )
        self._session.add(record)
        self._session.flush()
        return _to_session(record)

    def get_session(self, session_id: UUID) -> SessionEntity | None:
        record = self._session.get(SessionRecord, session_id)
        return _to_session(record) if record else None

    def list_sessions(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        project_id: UUID | None = None,
        library_only: bool = False,
    ) -> tuple[list[SessionEntity], int]:
        statement = select(SessionRecord).where(SessionRecord.user_id == user_id)
        if library_only:
            statement = statement.where(SessionRecord.project_id.is_(None))
        elif project_id is not None:
            statement = statement.where(SessionRecord.project_id == project_id)
        count_statement = statement.with_only_columns(func.count(SessionRecord.id))
        records = self._session.scalars(
            statement.order_by(
                SessionRecord.created_at.desc(),
                SessionRecord.id,
            )
            .limit(limit)
            .offset(offset),
        ).all()
        total = self._session.scalar(count_statement) or 0
        return [_to_session(record) for record in records], int(total)

    def list_sessions_of_project(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
    ) -> list[SessionEntity]:
        records = self._session.scalars(
            select(SessionRecord)
            .where(
                SessionRecord.user_id == user_id,
                SessionRecord.project_id == project_id,
            )
            .order_by(SessionRecord.created_at),
        ).all()
        return [_to_session(record) for record in records]

    def update_session(self, session_id: UUID, *, title: str) -> SessionEntity | None:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            return None
        record.title = title
        self._session.flush()
        return _to_session(record)

    def touch(self, session_id: UUID, *, at: datetime) -> None:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            return
        record.last_activity_at = at
        self._session.flush()

    def delete_session(self, session_id: UUID) -> None:
        record = self._session.get(SessionRecord, session_id)
        if record is not None:
            self._session.delete(record)
            self._session.flush()

    # Pending messages ------------------------------------------------------
    def enqueue(
        self,
        *,
        session_id: UUID,
        delivery: Delivery,
        content: str,
    ) -> PendingMessage:
        next_position = (
            self._session.scalar(
                select(func.coalesce(func.max(PendingMessageRecord.position), 0)).where(
                    PendingMessageRecord.session_id == session_id,
                    PendingMessageRecord.delivery == delivery.value,
                ),
            )
            or 0
        ) + 1
        record = PendingMessageRecord(
            session_id=session_id,
            delivery=delivery.value,
            position=next_position,
            content=content,
        )
        self._session.add(record)
        self._session.flush()
        return _to_pending(record)

    def list_pending(self, session_id: UUID) -> list[PendingMessage]:
        records = self._session.scalars(
            select(PendingMessageRecord)
            .where(PendingMessageRecord.session_id == session_id)
            .order_by(
                PendingMessageRecord.delivery,
                PendingMessageRecord.position,
            ),
        ).all()
        return [_to_pending(record) for record in records]

    def pending_counts(self, session_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
        if not session_ids:
            return {}
        rows = self._session.execute(
            select(
                PendingMessageRecord.session_id,
                PendingMessageRecord.delivery,
                func.count(PendingMessageRecord.id),
            )
            .where(PendingMessageRecord.session_id.in_(session_ids))
            .group_by(PendingMessageRecord.session_id, PendingMessageRecord.delivery),
        ).all()
        counts: dict[UUID, dict[str, int]] = {}
        for session_id, delivery, count in rows:
            counts.setdefault(session_id, {})[str(delivery)] = int(count)
        return counts

    def dequeue_next(
        self,
        *,
        session_id: UUID,
        delivery: Delivery,
    ) -> PendingMessage | None:
        record = self._session.scalar(
            select(PendingMessageRecord)
            .where(
                PendingMessageRecord.session_id == session_id,
                PendingMessageRecord.delivery == delivery.value,
            )
            .order_by(PendingMessageRecord.position)
            .limit(1)
            .with_for_update(skip_locked=True),
        )
        if record is None:
            return None
        pending = _to_pending(record)
        self._session.delete(record)
        self._session.flush()
        return pending

    def clear_pending(self, session_id: UUID) -> int:
        records = self._session.scalars(
            select(PendingMessageRecord).where(
                PendingMessageRecord.session_id == session_id,
            ),
        ).all()
        for record in records:
            self._session.delete(record)
        self._session.flush()
        return len(records)

    # Citations -------------------------------------------------------------
    def add_citation(
        self,
        *,
        session_id: UUID,
        citation_id: str,
        user_paper_id: UUID,
        snippet: str,
        chunk_ids: list[UUID] | None = None,
        title_path: str | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
    ) -> Citation:
        record = CitationRecord(
            session_id=session_id,
            citation_id=citation_id,
            user_paper_id=user_paper_id,
            chunk_ids=[str(item) for item in (chunk_ids or [])],
            title_path=title_path,
            snippet=snippet,
            page_start=page_start,
            page_end=page_end,
        )
        self._session.add(record)
        self._session.flush()
        return _to_citation(record)

    def get_citation(self, *, session_id: UUID, citation_id: str) -> Citation | None:
        record = self._session.scalar(
            select(CitationRecord).where(
                CitationRecord.session_id == session_id,
                CitationRecord.citation_id == citation_id,
            ),
        )
        return _to_citation(record) if record else None

    def commit(self) -> None:
        self._session.commit()

    def expire_all(self) -> None:
        self._session.expire_all()

    def rollback(self) -> None:
        self._session.rollback()


def _to_session(record: SessionRecord) -> SessionEntity:
    return SessionEntity(
        id=record.id,
        user_id=record.user_id,
        project_id=record.project_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_pending(record: PendingMessageRecord) -> PendingMessage:
    return PendingMessage(
        id=record.id,
        session_id=record.session_id,
        delivery=Delivery(record.delivery),
        position=record.position,
        content=record.content,
        created_at=record.created_at,
    )


def _to_citation(record: CitationRecord) -> Citation:
    return Citation(
        citation_id=record.citation_id,
        session_id=record.session_id,
        user_paper_id=record.user_paper_id,
        chunk_ids=[UUID(str(item)) for item in (record.chunk_ids or [])],
        title_path=record.title_path,
        snippet=record.snippet,
        page_start=record.page_start,
        page_end=record.page_end,
        created_at=record.created_at,
    )
