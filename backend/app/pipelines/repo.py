"""Persistence for downloads, runs and the users each of them serves."""

from dataclasses import dataclass
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
    and_,
    func,
    or_,
    select,
    text,
    update,
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
    next_stage,
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
    status: Mapped[str] = mapped_column(String(16), nullable=False)
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
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
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


@dataclass(frozen=True, slots=True)
class UserRunRequest:
    """One user's request for a run, plus the project it asked for."""

    user_id: UUID
    project_id: UUID | None = None
    run_id: UUID | None = None
    paper_id: UUID | None = None
    created_at: datetime | None = None


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
        Index(
            "ix_runs_stage_queue",
            "current_stage",
            "created_at",
            postgresql_where=text(
                "status = 'pending' AND next_attempt_at IS NULL"
            ),
        ),
    )

    paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stage_timings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Failures per stage, e.g. {"parse": 2}. Cleared when a run is retried.
    stage_attempts: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: When the current stage may be tried again; null means "right now".
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    #: The project this request also files the paper into, if any.
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
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

    def get_many(self, run_ids: list[UUID]) -> dict[UUID, Run]:
        records = self._session.scalars(
            select(RunRecord).where(RunRecord.id.in_(run_ids))
        ).all()
        return {record.id: _to_run(record) for record in records}

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

    def add_user(
        self,
        *,
        user_id: UUID,
        run: Run,
        project_id: UUID | None = None,
    ) -> None:
        """Record that this user asked for the run; one row per (user, run).

        A later request for the same paper may name a project, so an existing
        row without one absorbs it instead of being duplicated.
        """
        existing = self._session.scalar(
            select(UserRunRecord)
            .where(UserRunRecord.user_id == user_id)
            .where(UserRunRecord.run_id == run.id),
        )
        if existing is not None:
            if project_id is not None and existing.project_id is None:
                existing.project_id = project_id
                self._session.flush()
            return
        self._session.add(
            UserRunRecord(
                user_id=user_id,
                run_id=run.id,
                paper_id=run.paper_id,
                project_id=project_id,
            )
        )
        self._session.flush()

    def requests_of_run(self, run_id: UUID) -> list[UserRunRequest]:
        """Everyone waiting on this run, with the project each asked for."""
        rows = self._session.scalars(
            select(UserRunRecord).where(UserRunRecord.run_id == run_id),
        ).all()
        return [
            UserRunRequest(
                user_id=row.user_id, project_id=row.project_id
            )
            for row in rows
        ]

    def list_requests_for_user(
        self, *, user_id: UUID, limit: int
    ) -> list[UserRunRequest]:
        """This user's requests, newest first."""
        rows = self._session.scalars(
            select(UserRunRecord)
            .where(UserRunRecord.user_id == user_id)
            .order_by(UserRunRecord.created_at.desc(), UserRunRecord.id.desc())
            .limit(limit),
        ).all()
        return [
            UserRunRequest(
                user_id=row.user_id,
                project_id=row.project_id,
                run_id=row.run_id,
                paper_id=row.paper_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def user_ids_of(self, run_id: UUID) -> list[UUID]:
        return list(
            self._session.scalars(
                select(UserRunRecord.user_id).where(UserRunRecord.run_id == run_id),
            ).all()
        )

    # Queue -----------------------------------------------------------------
    def claim_next(self, *, stage: RunStage, lease_seconds: int) -> UUID | None:
        """Take the oldest run waiting for this stage and lease it.

        A run is claimed one stage at a time, so each stage gets its own share
        of the executor pool. Rows still waiting out a backoff carry a
        `next_attempt_at` and are skipped until it passes.
        """
        now = _now()
        record = self._session.scalar(
            select(RunRecord)
            .where(RunRecord.status == RunStatus.PENDING.value)
            .where(RunRecord.current_stage == stage.value)
            .where(
                or_(
                    RunRecord.next_attempt_at.is_(None),
                    RunRecord.next_attempt_at <= now,
                )
            )
            .order_by(RunRecord.created_at, RunRecord.id)
            .with_for_update(skip_locked=True)
            .limit(1),
        )
        if record is None:
            return None
        record.status = RunStatus.RUNNING.value
        record.next_attempt_at = None
        record.started_at = record.started_at or now
        record.leased_until = now + timedelta(seconds=lease_seconds)
        run_id = record.id
        self._session.commit()
        return run_id

    def defer_stage(
        self,
        run_id: UUID,
        *,
        stage: RunStage,
        error_message: str,
        max_attempts: int,
        base_seconds: float,
        max_seconds: float,
    ) -> int:
        """Record a failed stage and decide whether it may be retried.

        Under the limit the run goes back to pending with a future
        `next_attempt_at`; at the limit it fails for good and the error stays
        for the reader. Returns the new attempt count.
        """
        from ..platform.backoff import next_attempt_at

        record = self._session.scalar(
            select(RunRecord).where(RunRecord.id == run_id).with_for_update()
        )
        if record is None or record.status != RunStatus.RUNNING.value:
            self._session.rollback()
            return 0
        attempts = dict(record.stage_attempts or {})
        count = int(attempts.get(stage.value, 0)) + 1
        attempts[stage.value] = count
        record.stage_attempts = attempts
        record.error_message = error_message
        record.leased_until = None
        if count >= max_attempts:
            record.status = RunStatus.FAILED.value
            record.finished_at = _now()
            record.next_attempt_at = None
        else:
            record.status = RunStatus.PENDING.value
            record.current_stage = stage.value
            record.next_attempt_at = next_attempt_at(
                count,
                base_seconds=base_seconds,
                max_seconds=max_seconds,
            )
        self._session.flush()
        return count

    def advance_stage(self, run_id: UUID, *, completed: RunStage) -> bool:
        """Move to the next stage, or finish the run when that was the last.

        Returns whether the run is finished.
        """
        record = self._session.scalar(
            select(RunRecord).where(RunRecord.id == run_id).with_for_update()
        )
        if record is None or record.status != RunStatus.RUNNING.value:
            self._session.rollback()
            return False
        following = next_stage(completed)
        # A new stage starts with a clean slate: no backoff to wait out.
        record.next_attempt_at = None
        record.leased_until = None
        if following is None:
            record.status = RunStatus.SUCCESS.value
            record.current_stage = None
            record.error_message = None
            record.finished_at = _now()
            self._session.flush()
            return True
        record.status = RunStatus.PENDING.value
        record.current_stage = following.value
        self._session.flush()
        return False

    def renew_lease(self, run_id: UUID, *, lease_seconds: int) -> bool:
        record = self._session.scalar(
            select(RunRecord).where(RunRecord.id == run_id).with_for_update()
        )
        if record is None or record.status != RunStatus.RUNNING.value:
            return False
        record.leased_until = _now() + timedelta(seconds=lease_seconds)
        self._session.commit()
        return True

    def reclaim_expired(self) -> int:
        """Fail runs whose worker died, so the paper is not locked out forever."""
        records = self._session.scalars(
            select(RunRecord)
            .where(RunRecord.status == RunStatus.RUNNING.value)
            .where(RunRecord.leased_until.is_not(None))
            .where(RunRecord.leased_until < _now())
            .with_for_update(skip_locked=True),
        ).all()
        reclaimed = 0
        for record in records:
            # A slow but live executor still holds its advisory lock. Never
            # release the paper for another run while it can publish artifacts.
            available = self._session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"paper-run:{record.id}"},
            )
            if not available:
                continue
            record.status = RunStatus.FAILED.value
            record.error_message = "处理中断，请重试"
            record.finished_at = _now()
            record.leased_until = None
            reclaimed += 1
        self._session.commit()
        return reclaimed

    # Stage transitions -----------------------------------------------------
    def hold_ownership(self, run_id: UUID, *, lease_seconds: int) -> bool:
        """Confirm this executor may still publish the run.

        Pending means a direct caller owns the run by asking; running means a
        leased executor owns it, and only while the lease is alive. Anything
        terminal, or a running run whose lease expired, is not ours any more.
        """
        now = _now()
        held = self._session.execute(
            update(RunRecord)
            .where(RunRecord.id == run_id)
            .where(
                or_(
                    RunRecord.status == RunStatus.PENDING.value,
                    and_(
                        RunRecord.status == RunStatus.RUNNING.value,
                        RunRecord.leased_until > now,
                    ),
                )
            )
            .values(
                leased_until=func.coalesce(
                    RunRecord.leased_until, now + timedelta(seconds=lease_seconds)
                )
            )
            .execution_options(synchronize_session=False)
        )
        self._session.commit()
        return held.rowcount == 1

    def mark_stage_started(self, run_id: UUID, *, stage: RunStage) -> bool:
        """Assign the stage only while this run has not reached a terminal state."""
        now = _now()
        record = self._session.scalar(
            select(RunRecord).where(RunRecord.id == run_id).with_for_update()
        )
        if record is None or record.status not in (
            RunStatus.PENDING.value,
            RunStatus.RUNNING.value,
        ):
            self._session.rollback()
            return False
        timings = dict(record.stage_timings or {})
        timings[stage.value] = {"started_at": now.isoformat()}
        record.stage_timings = timings
        record.current_stage = stage.value
        record.status = RunStatus.RUNNING.value
        record.started_at = record.started_at or now
        self._session.flush()
        return True

    def publish_stage(self, run_id: UUID, *, stage: RunStage) -> bool:
        """Record a finished stage only if the run is still ours to publish."""
        record = self._session.scalar(
            select(RunRecord).where(RunRecord.id == run_id).with_for_update()
        )
        if record is None or record.status not in (
            RunStatus.PENDING.value,
            RunStatus.RUNNING.value,
        ):
            self._session.rollback()
            return False
        timings = dict(record.stage_timings or {})
        entry = dict(timings.get(stage.value) or {})
        entry["finished_at"] = _now().isoformat()
        timings[stage.value] = entry
        record.stage_timings = timings
        self._session.flush()
        return True

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
        project_id: UUID | None = None,
    ) -> Download:
        record = DownloadRecord(
            user_id=user_id,
            identifier_type=identifier_type,
            identifier=identifier,
            project_id=project_id,
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
        project_id=record.project_id,
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
        stage_attempts=dict(record.stage_attempts or {}),
        next_attempt_at=record.next_attempt_at,
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
