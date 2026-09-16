from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .domain import ImportStatus, PaperImport


class PaperImportRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "paper_imports"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_paper_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_papers.id", ondelete="SET NULL"),
        nullable=True,
    )
    identifier_type: Mapped[str] = mapped_column(String(16), nullable=False)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ImportRepository:
    """Persistence for identifier import attempts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        user_id: UUID,
        identifier_type: str,
        identifier: str,
        project_id: UUID | None,
    ) -> PaperImport:
        record = PaperImportRecord(
            user_id=user_id,
            project_id=project_id,
            identifier_type=identifier_type,
            identifier=identifier,
            status=ImportStatus.QUEUED.value,
        )
        self._session.add(record)
        self._session.flush()
        return _to_import(record)

    def get(self, import_id: UUID) -> PaperImport | None:
        record = self._session.get(PaperImportRecord, import_id)
        return _to_import(record) if record else None

    def list_for_user(self, *, user_id: UUID, limit: int) -> list[PaperImport]:
        records = self._session.scalars(
            select(PaperImportRecord)
            .where(PaperImportRecord.user_id == user_id)
            .order_by(PaperImportRecord.created_at.desc())
            .limit(limit),
        ).all()
        return [_to_import(record) for record in records]

    def mark_status(
        self,
        import_id: UUID,
        *,
        status: ImportStatus,
        error_code: str | None = None,
        metadata_source: str | None = None,
        user_paper_id: UUID | None = None,
    ) -> None:
        record = self._session.get(PaperImportRecord, import_id)
        if record is None:
            return
        record.status = status.value
        record.error_code = error_code
        if metadata_source is not None:
            record.metadata_source = metadata_source
        if user_paper_id is not None:
            record.user_paper_id = user_paper_id
        if status in {
            ImportStatus.PDF_UNAVAILABLE,
            ImportStatus.READY,
            ImportStatus.FAILED,
        }:
            record.finished_at = datetime.now(UTC)
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def expire_all(self) -> None:
        self._session.expire_all()

    def rollback(self) -> None:
        self._session.rollback()


def _to_import(record: PaperImportRecord) -> PaperImport:
    return PaperImport(
        id=record.id,
        user_id=record.user_id,
        project_id=record.project_id,
        user_paper_id=record.user_paper_id,
        identifier_type=record.identifier_type,
        identifier=record.identifier,
        status=ImportStatus(record.status),
        error_code=record.error_code,
        metadata_source=record.metadata_source,
        created_at=record.created_at,
        updated_at=record.updated_at,
        finished_at=record.finished_at,
    )
