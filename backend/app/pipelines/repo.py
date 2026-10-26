"""Persistence for downloads, runs and the users each of them serves."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .domain import (
    ACTIVE_RUN_STATUSES,
    Download,
    DownloadStatus,
    Run,
    RunStage,
    RunStatus,
    StageTiming,
)

logger = structlog.get_logger(__name__)


class DownloadRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One user's attempt to turn an identifier into a stored file.

    Never unique per identifier: the same identifier may yield different files
    over time, and only the file hash can decide whether two attempts agree.
    """

    __tablename__ = "downloads"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identifier_type: Mapped[str] = mapped_column(String(16), nullable=False)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    paper_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=True,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RunRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One processing attempt for a paper; stages folded into columns."""

    __tablename__ = "runs"
    __table_args__ = (
        Index(
            "uq_runs_one_active_per_paper",
            "paper_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    current_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stage_timings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Lease deadline: a run whose lease expired belongs to a worker that died.
    leased_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserRunRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Who asked for a run. Several users can share one run of one paper."""

    __tablename__ = "user_runs"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Redundant copy so a run's audience is one indexed query, not a join.
    paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _now() -> datetime:
    return datetime.now(UTC)


class RunRepository:
    """Persistence for runs, their lease and their audience."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, run_id: UUID) -> Run | None:
        record = self._session.get(RunRecord, run_id)
        return _to_run(record) if record else None

    def active_for_paper(self, paper_id: UUID) -> Run | None:
        record = self._session.scalar(
            select(RunRecord)
            .where(RunRecord.paper_id == paper_id)
            .where(
                RunRecord.status.in_([item.value for item in ACTIVE_RUN_STATUSES])
            ),
        )
        return _to_run(record) if record else None

    def latest_for_paper(self, paper_id: UUID) -> Run | None:
        record = self._session.scalar(
            select(RunRecord)
            .where(RunRecord.paper_id == paper_id)
            .order_by(RunRecord.created_at.desc())
            .limit(1),
        )
        return _to_run(record) if record else None

    def latest_for_papers(self, paper_ids: list[UUID]) -> dict[UUID, Run]:
        if not paper_ids:
            return {}
        records = self._session.scalars(
            select(RunRecord)
            .where(RunRecord.paper_id.in_(paper_ids))
            .order_by(RunRecord.paper_id, RunRecord.created_at.desc()),
        ).all()
        found: dict[UUID, Run] = {}
        for record in records:
            found.setdefault(record.paper_id, _to_run(record))
        return found

    def add(self, paper_id: UUID) -> Run:
        """Start a fresh run; the partial unique index forbids a second active one."""
        record = RunRecord(
            paper_id=paper_id,
            status=RunStatus.PENDING.value,
            current_stage=RunStage.PARSE.value,
            stage_timings={},
        )
        self._session.add(record)
        self._session.flush()
        return _to_run(record)

    def add_user(self, *, user_id: UUID, run: Run) -> None:
        """Record that this user asked for the run; one row per (user, run)."""
        existing = self._session.scalar(
            select(UserRunRecord.id)
            .where(UserRunRecord.user_id == user_id)
            .where(UserRunRecord.run_id == run.id),
        )
        if existing is not None:
            return
        self._session.add(
            UserRunRecord(user_id=user_id, run_id=run.id, paper_id=run.paper_id)
        )
        self._session.flush()

    def user_ids_of(self, run_id: UUID) -> list[UUID]:
        return list(
            self._session.scalars(
                select(UserRunRecord.user_id).where(UserRunRecord.run_id == run_id),
            ).all()
        )

    # Queue -----------------------------------------------------------------
    def claim_next(self, *, lease_seconds: int) -> UUID | None:
        """Take the oldest active run and hold a lease on it."""
        record = self._session.scalar(
            select(RunRecord)
            .where(
                RunRecord.status.in_(
                    [RunStatus.PENDING.value, RunStatus.RUNNING.value]
                )
            )
            .order_by(RunRecord.created_at, RunRecord.id)
            .with_for_update(skip_locked=True)
            .limit(1),
        )
        if record is None:
            return None
        record.status = RunStatus.RUNNING.value
        record.started_at = record.started_at or _now()
        record.leased_until = _now() + timedelta(seconds=lease_seconds)
        run_id = record.id
        self._session.commit()
        return run_id

    def renew_lease(self, run_id: UUID, *, lease_seconds: int) -> None:
        record = self._session.get(RunRecord, run_id)
        if record is None:
            return
        record.leased_until = _now() + timedelta(seconds=lease_seconds)
        self._session.commit()

    def reclaim_expired(self) -> int:
        """Fail runs whose worker died, so the paper is not locked out forever."""
        records = self._session.scalars(
            select(RunRecord)
            .where(RunRecord.status == RunStatus.RUNNING.value)
            .where(RunRecord.leased_until.is_not(None))
            .where(RunRecord.leased_until < _now()),
        ).all()
        for record in records:
            record.status = RunStatus.FAILED.value
            record.error_message = "处理中断，请重试"
            record.finished_at = _now()
            record.leased_until = None
        self._session.commit()
        return len(records)

    # Stage transitions -----------------------------------------------------
    def mark_stage_started(self, run_id: UUID, *, stage: RunStage) -> None:
        record = self._session.get(RunRecord, run_id)
        if record is None:
            return
        record.status = RunStatus.RUNNING.value
        record.current_stage = stage.value
        record.started_at = record.started_at or _now()
        timings = dict(record.stage_timings or {})
        timings[stage.value] = {"started_at": _now().isoformat()}
        record.stage_timings = timings
        self._session.flush()

    def mark_stage_finished(self, run_id: UUID, *, stage: RunStage) -> None:
        record = self._session.get(RunRecord, run_id)
        if record is None:
            return
        timings = dict(record.stage_timings or {})
        entry = dict(timings.get(stage.value) or {})
        entry["finished_at"] = _now().isoformat()
        timings[stage.value] = entry
        record.stage_timings = timings
        self._session.flush()

    def finish_success(self, run_id: UUID) -> None:
        record = self._session.get(RunRecord, run_id)
        if record is None:
            return
        record.status = RunStatus.SUCCESS.value
        record.current_stage = None
        record.error_message = None
        record.finished_at = _now()
        record.leased_until = None
        self._session.flush()

    def finish_failure(self, run_id: UUID, *, error_message: str) -> None:
        record = self._session.get(RunRecord, run_id)
        if record is None:
            return
        record.status = RunStatus.FAILED.value
        record.error_message = error_message
        record.finished_at = _now()
        record.leased_until = None
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def expire_all(self) -> None:
        self._session.expire_all()


class DownloadRepository:
    """Persistence for the per-user download attempts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        user_id: UUID,
        identifier_type: str,
        identifier: str,
    ) -> Download:
        record = DownloadRecord(
            user_id=user_id,
            identifier_type=identifier_type,
            identifier=identifier,
            status=DownloadStatus.PENDING.value,
        )
        self._session.add(record)
        self._session.flush()
        return _to_download(record)

    def get(self, download_id: UUID) -> Download | None:
        record = self._session.get(DownloadRecord, download_id)
        return _to_download(record) if record else None

    def list_for_user(self, *, user_id: UUID, limit: int) -> list[Download]:
        records = self._session.scalars(
            select(DownloadRecord)
            .where(DownloadRecord.user_id == user_id)
            .order_by(DownloadRecord.created_at.desc(), DownloadRecord.id.desc())
            .limit(limit),
        ).all()
        return [_to_download(record) for record in records]

    def list_for_paper(self, paper_id: UUID) -> list[Download]:
        records = self._session.scalars(
            select(DownloadRecord)
            .where(DownloadRecord.paper_id == paper_id)
            .order_by(DownloadRecord.created_at),
        ).all()
        return [_to_download(record) for record in records]

    # Queue -----------------------------------------------------------------
    def claim_next(self) -> UUID | None:
        record = self._session.scalar(
            select(DownloadRecord)
            .where(DownloadRecord.status == DownloadStatus.PENDING.value)
            .order_by(DownloadRecord.created_at, DownloadRecord.id)
            .with_for_update(skip_locked=True)
            .limit(1),
        )
        if record is None:
            return None
        record.status = DownloadStatus.RUNNING.value
        record.started_at = _now()
        download_id = record.id
        self._session.commit()
        return download_id

    def recover_interrupted(self) -> int:
        """Return downloads interrupted mid-run to the queue."""
        records = self._session.scalars(
            select(DownloadRecord).where(
                DownloadRecord.status == DownloadStatus.RUNNING.value
            )
        ).all()
        for record in records:
            record.status = DownloadStatus.PENDING.value
            record.started_at = None
        self._session.commit()
        return len(records)

    # Outcomes --------------------------------------------------------------
    def finish_success(
        self,
        download_id: UUID,
        *,
        paper_id: UUID,
        run_id: UUID,
        source_url: str | None,
    ) -> None:
        record = self._session.get(DownloadRecord, download_id)
        if record is None:
            return
        record.status = DownloadStatus.SUCCESS.value
        record.paper_id = paper_id
        record.run_id = run_id
        record.source_url = source_url
        record.error_message = None
        record.finished_at = _now()
        self._session.flush()

    def finish_failure(self, download_id: UUID, *, error_message: str) -> None:
        record = self._session.get(DownloadRecord, download_id)
        if record is None:
            return
        record.status = DownloadStatus.FAILED.value
        record.error_message = error_message
        record.finished_at = _now()
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def expire_all(self) -> None:
        self._session.expire_all()


def _to_download(record: DownloadRecord) -> Download:
    return Download(
        id=record.id,
        user_id=record.user_id,
        identifier_type=record.identifier_type,
        identifier=record.identifier,
        status=DownloadStatus(record.status),
        paper_id=record.paper_id,
        run_id=record.run_id,
        source_url=record.source_url,
        error_message=record.error_message,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _to_run(record: RunRecord) -> Run:
    timings: dict[str, StageTiming] = {}
    for name, value in (record.stage_timings or {}).items():
        if not isinstance(value, dict):
            continue
        timings[name] = StageTiming(
            started_at=_parse_time(value.get("started_at")),
            finished_at=_parse_time(value.get("finished_at")),
        )
    return Run(
        id=record.id,
        paper_id=record.paper_id,
        status=RunStatus(record.status),
        current_stage=(
            RunStage(record.current_stage) if record.current_stage else None
        ),
        stage_timings=timings,
        error_message=record.error_message,
        leased_until=record.leased_until,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
