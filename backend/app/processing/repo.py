from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.platform.database import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.processing.domain import (
    IngestionJob,
    IngestionStage,
    IngestionStageRecord,
    IngestionStatus,
    StageStatus,
)


class IngestionJobRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class IngestionStageRecordOrm(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_stages"
    __table_args__ = (
        UniqueConstraint("ingestion_job_id", "stage", name="uq_ingestion_stage"),
    )

    ingestion_job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
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


def _now() -> datetime:
    return datetime.now(UTC)


class IngestionRepository:
    """Persistence for ingestion jobs and their per-stage state."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_job(
        self,
        *,
        paper_id: UUID,
        stages: tuple[IngestionStage, ...],
    ) -> IngestionJob:
        job = IngestionJobRecord(
            paper_id=paper_id,
            status=IngestionStatus.QUEUED.value,
        )
        self._session.add(job)
        self._session.flush()
        for stage in stages:
            self._session.add(
                IngestionStageRecordOrm(
                    ingestion_job_id=job.id,
                    stage=stage.value,
                    status=StageStatus.PENDING.value,
                ),
            )
        self._session.flush()
        job_id = job.id
        self._session.refresh(job)
        loaded = self.get_job(job_id)
        if loaded is None:  # pragma: no cover - defensive
            raise LookupError(f"ingestion job {job_id} disappeared after insert")
        return loaded

    def get_job(self, job_id: UUID) -> IngestionJob | None:
        record = self._session.get(IngestionJobRecord, job_id)
        if record is None:
            return None
        return _to_job(record, self._stages_of([job_id]).get(job_id, []))

    def latest_job_for_paper(self, paper_id: UUID) -> IngestionJob | None:
        return self.latest_jobs_for_papers([paper_id]).get(paper_id)

    def active_job_for_paper(self, paper_id: UUID) -> IngestionJob | None:
        record = self._session.scalar(
            select(IngestionJobRecord)
            .where(
                IngestionJobRecord.paper_id == paper_id,
                IngestionJobRecord.status.in_(
                    [IngestionStatus.QUEUED.value, IngestionStatus.RUNNING.value],
                ),
            )
            .order_by(IngestionJobRecord.created_at.desc())
            .limit(1),
        )
        if record is None:
            return None
        return _to_job(record, self._stages_of([record.id]).get(record.id, []))

    def claim_next_queued_job(self) -> UUID | None:
        record = self._session.scalar(
            select(IngestionJobRecord)
            .where(IngestionJobRecord.status == IngestionStatus.QUEUED.value)
            .order_by(IngestionJobRecord.created_at, IngestionJobRecord.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if record is None:
            return None
        record.status = IngestionStatus.RUNNING.value
        record.started_at = record.started_at or _now()
        job_id = record.id
        self._session.commit()
        return job_id

    def recover_interrupted_jobs(self) -> int:
        records = self._session.scalars(
            select(IngestionJobRecord).where(
                IngestionJobRecord.status == IngestionStatus.RUNNING.value
            )
        ).all()
        for record in records:
            record.status = IngestionStatus.QUEUED.value
            record.current_stage = None
            for stage in self._stages_of([record.id]).get(record.id, []):
                if stage.status == StageStatus.RUNNING.value:
                    stage.status = StageStatus.PENDING.value
                    stage.started_at = None
        self._session.commit()
        return len(records)

    def latest_jobs_for_papers(
        self,
        paper_ids: list[UUID],
    ) -> dict[UUID, IngestionJob]:
        """Return the newest job per paper, in one round trip per table."""
        if not paper_ids:
            return {}
        records = self._session.scalars(
            select(IngestionJobRecord)
            .where(IngestionJobRecord.paper_id.in_(paper_ids))
            .order_by(IngestionJobRecord.created_at.desc()),
        ).all()
        latest: dict[UUID, IngestionJobRecord] = {}
        for record in records:
            latest.setdefault(record.paper_id, record)
        if not latest:
            return {}
        stages = self._stages_of([record.id for record in latest.values()])
        return {
            paper_id: _to_job(record, stages.get(record.id, []))
            for paper_id, record in latest.items()
        }

    # State transitions -----------------------------------------------------
    def mark_running(self, job_id: UUID, *, stage: IngestionStage) -> None:
        job = self._session.get(IngestionJobRecord, job_id)
        if job is None:
            return
        now = _now()
        job.status = IngestionStatus.RUNNING.value
        job.current_stage = stage.value
        job.started_at = job.started_at or now
        stage_record = self._stage_record(job_id, stage)
        stage_record.status = StageStatus.RUNNING.value
        stage_record.started_at = now
        self._session.flush()

    def mark_stage_succeeded(
        self,
        job_id: UUID,
        *,
        stage: IngestionStage,
        progress: dict | None = None,
    ) -> None:
        record = self._stage_record(job_id, stage)
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
        job_id: UUID,
        *,
        stage: IngestionStage,
        error_code: str,
        error_message: str | None = None,
    ) -> None:
        record = self._stage_record(job_id, stage)
        record.status = StageStatus.FAILED.value
        record.attempt = record.attempt + 1
        record.finished_at = _now()
        record.error_code = error_code
        record.error_message = error_message
        self._session.flush()

    def mark_stage_skipped(self, job_id: UUID, *, stage: IngestionStage) -> None:
        record = self._stage_record(job_id, stage)
        record.status = StageStatus.SKIPPED.value
        record.finished_at = _now()
        self._session.flush()

    def finish_job(self, job_id: UUID, *, error_code: str | None = None) -> None:
        job = self._session.get(IngestionJobRecord, job_id)
        if job is None:
            return
        job.status = (
            IngestionStatus.SUCCEEDED.value
            if error_code is None
            else IngestionStatus.FAILED.value
        )
        job.error_code = error_code
        job.current_stage = None
        job.finished_at = _now()
        self._session.flush()

    def expire_all(self) -> None:
        """Drop cached state so out-of-band stage writes become visible."""
        self._session.expire_all()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    # Internals -------------------------------------------------------------
    def _stages_of(
        self,
        job_ids: list[UUID],
    ) -> dict[UUID, list[IngestionStageRecordOrm]]:
        if not job_ids:
            return {}
        records = self._session.scalars(
            select(IngestionStageRecordOrm)
            .where(IngestionStageRecordOrm.ingestion_job_id.in_(job_ids))
            .order_by(IngestionStageRecordOrm.created_at),
        ).all()
        grouped: dict[UUID, list[IngestionStageRecordOrm]] = {}
        for record in records:
            grouped.setdefault(record.ingestion_job_id, []).append(record)
        return grouped

    def _stage_record(
        self,
        job_id: UUID,
        stage: IngestionStage,
    ) -> IngestionStageRecordOrm:
        record = self._session.scalar(
            select(IngestionStageRecordOrm).where(
                IngestionStageRecordOrm.ingestion_job_id == job_id,
                IngestionStageRecordOrm.stage == stage.value,
            ),
        )
        if record is None:
            raise LookupError(f"ingestion stage {stage} missing for job {job_id}")
        return record


def _to_job(
    record: IngestionJobRecord,
    stages: list[IngestionStageRecordOrm],
) -> IngestionJob:
    return IngestionJob(
        id=record.id,
        paper_id=record.paper_id,
        status=IngestionStatus(record.status),
        current_stage=(
            IngestionStage(record.current_stage) if record.current_stage else None
        ),
        error_code=record.error_code,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        stages=tuple(
            IngestionStageRecord(
                id=stage.id,
                stage=IngestionStage(stage.stage),
                status=StageStatus(stage.status),
                attempt=stage.attempt,
                error_code=stage.error_code,
                error_message=stage.error_message,
                progress=stage.progress,
                started_at=stage.started_at,
                finished_at=stage.finished_at,
                updated_at=stage.updated_at,
            )
            for stage in stages
        ),
    )
