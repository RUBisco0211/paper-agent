"""Persistence for approvals and the downloads a request creates."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..pipelines.domain import Download
from ..pipelines.repo import DownloadRepository
from ..platform.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ImportApprovalRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "import_approvals"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False)
    results: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ImportRepository:
    """Queue a user's downloads; the download itself is owned by pipelines."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_download(
        self,
        *,
        user_id: UUID,
        identifier_type: str,
        identifier: str,
        project_id: UUID | None = None,
    ) -> Download:
        return DownloadRepository(self._session).add(
            user_id=user_id,
            identifier_type=identifier_type,
            identifier=identifier,
            project_id=project_id,
        )


class ImportApprovalRepository:
    """Persistence for user-approved discovery batches."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        candidates: list[dict],
        expires_at: datetime,
    ) -> ImportApprovalRecord:
        record = ImportApprovalRecord(
            user_id=user_id,
            session_id=session_id,
            candidates=candidates,
            status="pending",
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def latest_for_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        for_update: bool = False,
    ) -> ImportApprovalRecord | None:
        statement = (
            select(ImportApprovalRecord)
            .where(
                ImportApprovalRecord.user_id == user_id,
                ImportApprovalRecord.session_id == session_id,
            )
            .order_by(
                ImportApprovalRecord.created_at.desc(),
                ImportApprovalRecord.id.desc(),
            )
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def commit(self) -> None:
        self._session.commit()
