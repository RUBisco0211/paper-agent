"""The worker drains downloads first, then runs, and reclaims dead runs."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.library.repo import PaperRepository
from app.pipelines.domain import DownloadStatus, RunStage, RunStatus
from app.pipelines.repo import DownloadRepository, RunRepository


@pytest.fixture(autouse=True)
def _clean(clean_tables) -> None:
    """Each case starts from an empty database."""


def _add_paper(session_factory: sessionmaker[Session]) -> object:
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="a" * 64, byte_size=100, page_count=1
        )
        session.commit()
        return paper


def test_a_run_carries_its_lease_so_a_dead_worker_is_detectable(
    session_factory: sessionmaker[Session],
) -> None:
    paper = _add_paper(session_factory)
    with session_factory() as session:
        runs = RunRepository(session)
        runs.add(paper.id)
        session.commit()

    with session_factory() as session:
        claimed = RunRepository(session).claim_next(lease_seconds=60)

    with session_factory() as session:
        run = RunRepository(session).get(claimed)
        assert run is not None
        assert run.status is RunStatus.RUNNING
        assert run.leased_until is not None
        assert run.leased_until > datetime.now(UTC)


def test_an_expired_lease_is_failed_so_the_paper_can_run_again(
    session_factory: sessionmaker[Session],
) -> None:
    paper = _add_paper(session_factory)
    with session_factory() as session:
        runs = RunRepository(session)
        run = runs.add(paper.id)
        session.commit()

    with session_factory() as session:
        RunRepository(session).claim_next(lease_seconds=60)

    # Simulate a worker that stopped renewing its lease.
    from app.pipelines.repo import RunRecord

    with session_factory() as session:
        record = session.get(RunRecord, run.id)
        assert record is not None
        record.leased_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    with session_factory() as session:
        assert RunRepository(session).reclaim_expired() == 1

    with session_factory() as session:
        reclaimed = RunRepository(session).get(run.id)
        assert reclaimed is not None
        assert reclaimed.status is RunStatus.FAILED
        assert reclaimed.error_message is not None


def test_a_renewed_lease_keeps_its_run_alive(
    session_factory: sessionmaker[Session],
) -> None:
    paper = _add_paper(session_factory)
    with session_factory() as session:
        RunRepository(session).add(paper.id)
        session.commit()

    with session_factory() as session:
        runs = RunRepository(session)
        run_id = runs.claim_next(lease_seconds=60)
    with session_factory() as session:
        RunRepository(session).renew_lease(run_id, lease_seconds=60)

    with session_factory() as session:
        assert RunRepository(session).reclaim_expired() == 0

    with session_factory() as session:
        run = RunRepository(session).get(run_id)
        assert run is not None
        assert run.status is RunStatus.RUNNING


def test_only_one_run_per_paper_can_be_active(
    session_factory: sessionmaker[Session],
) -> None:
    """A second starter loses the race instead of doubling the work."""
    paper = _add_paper(session_factory)
    with session_factory() as session:
        runs = RunRepository(session)
        first = runs.add(paper.id)
        session.commit()

    with session_factory() as session:
        active = RunRepository(session).active_for_paper(paper.id)
        assert active is not None
        assert active.id == first.id


def test_a_run_moves_to_the_next_stage_only_after_the_current_one(
    session_factory: sessionmaker[Session],
) -> None:
    paper = _add_paper(session_factory)
    with session_factory() as session:
        runs = RunRepository(session)
        run = runs.add(paper.id)
        session.commit()
        assert run.current_stage is RunStage.PARSE

        runs.mark_stage_started(run.id, stage=RunStage.PARSE)
        runs.mark_stage_finished(run.id, stage=RunStage.PARSE)
        runs.finish_success(run.id)
        session.commit()

    with session_factory() as session:
        finished = RunRepository(session).get(run.id)
        assert finished is not None
        assert finished.status is RunStatus.SUCCESS
        assert finished.current_stage is None
        timing = finished.timing(RunStage.PARSE)
        assert timing.started_at is not None
        assert timing.finished_at is not None


def test_a_download_is_claimed_once(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        downloads = DownloadRepository(session)
        record = downloads.add(
            user_id=_user_id(session), identifier_type="doi", identifier="10.1/x"
        )
        session.commit()
        download_id = record.id

    with session_factory() as session:
        assert DownloadRepository(session).claim_next() == download_id
    with session_factory() as session:
        assert DownloadRepository(session).claim_next() is None


def test_an_interrupted_download_returns_to_the_queue(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        downloads = DownloadRepository(session)
        downloads.add(
            user_id=_user_id(session), identifier_type="doi", identifier="10.1/y"
        )
        session.commit()

    with session_factory() as session:
        DownloadRepository(session).claim_next()
    with session_factory() as session:
        assert DownloadRepository(session).recover_interrupted() == 1
    with session_factory() as session:
        assert DownloadRepository(session).claim_next() is not None


def test_a_failed_download_keeps_its_row_and_reason(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        downloads = DownloadRepository(session)
        record = downloads.add(
            user_id=_user_id(session), identifier_type="doi", identifier="10.1/z"
        )
        session.commit()

    with session_factory() as session:
        repository = DownloadRepository(session)
        repository.finish_failure(record.id, error_message="没有找到可用的原文")
        session.commit()

    with session_factory() as session:
        stored = DownloadRepository(session).get(record.id)
        assert stored is not None
        assert stored.status is DownloadStatus.FAILED
        assert stored.error_message == "没有找到可用的原文"
        assert stored.run_id is None


def _user_id(session: Session):
    from app.auth.repo import UserRecord

    user = session.query(UserRecord).first()
    if user is None:
        user = UserRecord(
            email=f"worker-{datetime.now(UTC).timestamp()}@example.com",
            password_hash="x",
            display_name="Worker",
        )
        session.add(user)
        session.flush()
    return user.id
