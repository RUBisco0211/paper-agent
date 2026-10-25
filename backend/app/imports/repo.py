from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from .domain import (
    ACTIVE_STATUSES,
    STAGE_ORDER,
    ImportStage,
    ImportStageRecord,
    ImportStatus,
    PaperImport,
    StageStatus,
)


class PaperImportRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """How one paper entered the library: at most one row per paper."""

    __tablename__ = "paper_imports"
    __table_args__ = (
        Index(
            "uq_paper_imports_one_per_paper",
            "paper_id",
            unique=True,
            postgresql_where=text("paper_id IS NOT NULL"),
        ),
    )

    paper_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=True,
    )
    initiated_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identifier_type: Mapped[str] = mapped_column(String(16), nullable=False)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ImportStageRecordOrm(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "import_stages"
    __table_args__ = (
        UniqueConstraint("import_id", "stage", name="uq_import_stage"),
    )

    import_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("paper_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


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


def _now() -> datetime:
    return datetime.now(UTC)


class ImportRepository:
    """Persistence for imports, their stage rows and approval batches."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # Creation and lookup ---------------------------------------------------
    def find_by_identifier(
        self,
        *,
        identifier_type: str,
        identifier: str,
    ) -> PaperImport | None:
        """The existing record for this identifier, if one was ever started."""
        record = self._session.scalar(
            select(PaperImportRecord)
            .where(PaperImportRecord.identifier_type == identifier_type)
            .where(PaperImportRecord.identifier == identifier)
            .order_by(PaperImportRecord.created_at.desc())
            .limit(1),
        )
        return self._to_import(record) if record else None

    def find_by_paper(self, paper_id: UUID) -> PaperImport | None:
        record = self._session.scalar(
            select(PaperImportRecord).where(PaperImportRecord.paper_id == paper_id),
        )
        return self._to_import(record) if record else None

    def add(
        self,
        *,
        initiated_by: UUID,
        identifier_type: str,
        identifier: str,
    ) -> PaperImport:
        record = PaperImportRecord(
            initiated_by=initiated_by,
            identifier_type=identifier_type,
            identifier=identifier,
            status=ImportStatus.QUEUED.value,
        )
        self._session.add(record)
        self._session.flush()
        for stage in STAGE_ORDER:
            self._session.add(
                ImportStageRecordOrm(
                    import_id=record.id,
                    stage=stage.value,
                    status=StageStatus.PENDING.value,
                ),
            )
        self._session.flush()
        import_id = record.id
        self._session.expire(record)
        loaded = self.get(import_id)
        if loaded is None:  # pragma: no cover - defensive
            raise LookupError(f"import {import_id} disappeared after insert")
        return loaded

    def reset_for_retry(self, import_id: UUID) -> None:
        """Requeue everything that failed or never ran, keeping what succeeded.

        A retry must not re-run a stage whose artifact is still in place: the
        provider quotas behind parsing and embedding are the scarce resource.
        """
        record = self._session.get(PaperImportRecord, import_id)
        if record is None:
            return
        record.status = ImportStatus.QUEUED.value
        record.error_code = None
        record.finished_at = None
        for stage in self._stages_of([import_id]).get(import_id, []):
            if stage.status == StageStatus.SUCCEEDED.value:
                continue
            stage.status = StageStatus.PENDING.value
            stage.error_code = None
            stage.error_message = None
            stage.started_at = None
            stage.finished_at = None
        self._session.flush()

    def get(self, import_id: UUID) -> PaperImport | None:
        record = self._session.get(PaperImportRecord, import_id)
        if record is None:
            return None
        return _to_import(record, self._stages_of([import_id]).get(import_id, []))

    def list_for_user(self, *, user_id: UUID, limit: int) -> list[PaperImport]:
        records = self._session.scalars(
            select(PaperImportRecord)
            .where(PaperImportRecord.initiated_by == user_id)
            .order_by(PaperImportRecord.created_at.desc())
            .limit(limit),
        ).all()
        stages = self._stages_of([record.id for record in records])
        return [
            _to_import(record, stages.get(record.id, [])) for record in records
        ]

    # Queue -----------------------------------------------------------------
    def claim_next_queued(self) -> UUID | None:
        record = self._session.scalar(
            select(PaperImportRecord)
            .where(PaperImportRecord.status == ImportStatus.QUEUED.value)
            .order_by(PaperImportRecord.created_at, PaperImportRecord.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if record is None:
            return None
        record.status = ImportStatus.RUNNING.value
        record.started_at = record.started_at or _now()
        import_id = record.id
        self._session.commit()
        return import_id

    def recover_interrupted(self) -> int:
        """Return imports interrupted mid-run to the queue."""
        records = self._session.scalars(
            select(PaperImportRecord).where(
                PaperImportRecord.status == ImportStatus.RUNNING.value
            )
        ).all()
        for record in records:
            record.status = ImportStatus.QUEUED.value
            for stage in self._stages_of([record.id]).get(record.id, []):
                if stage.status == StageStatus.RUNNING.value:
                    stage.status = StageStatus.PENDING.value
                    stage.started_at = None
        self._session.commit()
        return len(records)

    def active_for_paper(self, paper_id: UUID) -> PaperImport | None:
        record = self._session.scalar(
            select(PaperImportRecord).where(
                PaperImportRecord.paper_id == paper_id,
                PaperImportRecord.status.in_(
                    [status.value for status in ACTIVE_STATUSES]
                ),
            ),
        )
        return self._to_import(record) if record else None

    # State transitions -----------------------------------------------------
    def bind_paper(self, import_id: UUID, paper_id: UUID) -> None:
        record = self._session.get(PaperImportRecord, import_id)
        if record is None:
            return
        record.paper_id = paper_id
        self._session.flush()

    def mark_stage_running(self, import_id: UUID, *, stage: ImportStage) -> None:
        record = self._session.get(PaperImportRecord, import_id)
        if record is not None:
            record.status = ImportStatus.RUNNING.value
            record.started_at = record.started_at or _now()
        stage_record = self._stage_record(import_id, stage)
        stage_record.status = StageStatus.RUNNING.value
        stage_record.started_at = _now()
        self._session.flush()

    def mark_stage_succeeded(
        self,
        import_id: UUID,
        *,
        stage: ImportStage,
        progress: dict | None = None,
    ) -> None:
        record = self._stage_record(import_id, stage)
        record.status = StageStatus.SUCCEEDED.value
        record.attempt = record.attempt + 1
        record.finished_at = _now()
        record.error_code = None
        record.error_message = None
        if progress is not None:
            record.progress = progress
        self._session.flush()

    def mark_stage_failed(
        self,
        import_id: UUID,
        *,
        stage: ImportStage,
        error_code: str,
        error_message: str | None = None,
    ) -> None:
        record = self._stage_record(import_id, stage)
        record.status = StageStatus.FAILED.value
        record.attempt = record.attempt + 1
        record.finished_at = _now()
        record.error_code = error_code
        record.error_message = error_message
        self._session.flush()

    def finish(
        self,
        import_id: UUID,
        *,
        status: ImportStatus,
        error_code: str | None = None,
    ) -> None:
        record = self._session.get(PaperImportRecord, import_id)
        if record is None:
            return
        record.status = status.value
        record.error_code = error_code
        record.finished_at = _now()
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def expire_all(self) -> None:
        self._session.expire_all()

    def rollback(self) -> None:
        self._session.rollback()

    # Internals -------------------------------------------------------------
    def _stages_of(
        self, import_ids: list[UUID]
    ) -> dict[UUID, list[ImportStageRecordOrm]]:
        if not import_ids:
            return {}
        records = self._session.scalars(
            select(ImportStageRecordOrm)
            .where(ImportStageRecordOrm.import_id.in_(import_ids))
            .order_by(ImportStageRecordOrm.created_at),
        ).all()
        grouped: dict[UUID, list[ImportStageRecordOrm]] = {}
        for record in records:
            grouped.setdefault(record.import_id, []).append(record)
        return grouped

    def _stage_record(
        self,
        import_id: UUID,
        stage: ImportStage,
    ) -> ImportStageRecordOrm:
        record = self._session.scalar(
            select(ImportStageRecordOrm).where(
                ImportStageRecordOrm.import_id == import_id,
                ImportStageRecordOrm.stage == stage.value,
            ),
        )
        if record is None:
            raise LookupError(f"stage {stage} missing for import {import_id}")
        return record

    def _to_import(self, record: PaperImportRecord) -> PaperImport:
        return _to_import(record, self._stages_of([record.id]).get(record.id, []))


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


def _to_import(
    record: PaperImportRecord,
    stages: list[ImportStageRecordOrm],
) -> PaperImport:
    return PaperImport(
        id=record.id,
        paper_id=record.paper_id,
        initiated_by=record.initiated_by,
        identifier_type=record.identifier_type,
        identifier=record.identifier,
        status=ImportStatus(record.status),
        error_code=record.error_code,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        stages=tuple(
            ImportStageRecord(
                id=stage.id,
                stage=ImportStage(stage.stage),
                status=StageStatus(stage.status),
                attempt=stage.attempt,
                error_code=stage.error_code,
                error_message=stage.error_message,
                progress=stage.progress,
                started_at=stage.started_at,
                finished_at=stage.finished_at,
                updated_at=stage.updated_at,
            )
            for stage in sorted(
                stages, key=lambda item: _STAGE_RANK.get(item.stage, 0)
            )
        ),
    )


_STAGE_RANK = {stage.value: index for index, stage in enumerate(STAGE_ORDER)}
