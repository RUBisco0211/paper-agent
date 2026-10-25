from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.imports.domain import ImportStage, ImportStatus, StageStatus
from app.imports.queue import ImportQueueService
from app.imports.repo import ImportRepository
from app.library.repo import PaperRepository
from app.literature_support.importing.worker import ImportWorker
from app.platform.tasks import ApiTaskScheduler


class RecordingPipeline:
    def __init__(self) -> None:
        self.imports: list[UUID] = []

    def run_sync(self, import_id: UUID) -> None:
        self.imports.append(import_id)


def _user_id(client, api_prefix: str, token: str) -> UUID:
    return UUID(
        client.get(f"{api_prefix}/auth/me", headers={"Authorization": f"Bearer {token}"})
        .json()["id"]
    )


def _queued_import(
    db_session: Session,
    *,
    initiated_by: UUID,
    identifier: str,
    file_hash: str,
    page_count: int = 1,
) -> UUID:
    """A paper with a stored file and an import that still needs its stages."""
    papers = PaperRepository(db_session)
    paper = papers.get_or_add_paper(
        file_hash=file_hash, byte_size=100, page_count=page_count
    )
    imports = ImportRepository(db_session)
    record = imports.add(
        initiated_by=initiated_by,
        identifier_type="upload",
        identifier=identifier,
    )
    imports.bind_paper(record.id, paper.id)
    imports.mark_stage_succeeded(record.id, stage=ImportStage.SOURCE)
    db_session.commit()
    return record.id


def test_worker_runs_distinct_imports_concurrently_when_capacity_is_two(
    session_factory: sessionmaker[Session],
    db_session: Session,
    register_user,
    client,
    api_prefix,
) -> None:
    token = register_user(email="parallel-worker@example.com")["access_token"]
    user_id = _user_id(client, api_prefix, token)
    import_ids = [
        _queued_import(
            db_session,
            initiated_by=user_id,
            identifier=f"{count}.pdf",
            file_hash=f"{count}" * 64,
            page_count=count,
        )
        for count in (1, 2)
    ]

    observed: list[UUID] = []
    lock = Lock()

    class ParallelPipeline:
        def run_sync(self, import_id: UUID) -> None:
            with lock:
                observed.append(import_id)

    worker = ImportWorker(
        session_factory=session_factory, pipeline=ParallelPipeline()
    )
    assert worker.run_batch(max_concurrent_imports=2) == 2
    assert sorted(observed) == sorted(import_ids)


def test_api_scheduler_leaves_the_stages_to_the_worker() -> None:
    submitted: list[str] = []

    class RecordingScheduler:
        def submit(self, factory, *, name: str) -> None:
            submitted.append(name)

    scheduler = ApiTaskScheduler(RecordingScheduler())
    scheduler.submit(lambda: None, name="import:one")
    scheduler.submit(lambda: None, name="other:two")

    assert submitted == ["other:two"]


def test_worker_claims_a_queued_import(
    session_factory: sessionmaker[Session],
    db_session: Session,
    register_user,
    client,
    api_prefix,
) -> None:
    token = register_user(email="worker@example.com")["access_token"]
    user_id = _user_id(client, api_prefix, token)
    queued = _queued_import(
        db_session,
        initiated_by=user_id,
        identifier="worker.pdf",
        file_hash="w" * 64,
    )
    pipeline = RecordingPipeline()

    worker = ImportWorker(session_factory=session_factory, pipeline=pipeline)

    assert worker.run_once() is True
    assert pipeline.imports == [queued]


def test_worker_requeues_an_interrupted_import_when_it_restarts(
    session_factory: sessionmaker[Session],
    db_session: Session,
    register_user,
    client,
    api_prefix,
) -> None:
    token = register_user(email="restart@example.com")["access_token"]
    user_id = _user_id(client, api_prefix, token)
    import_id = _queued_import(
        db_session,
        initiated_by=user_id,
        identifier="restart.pdf",
        file_hash="r" * 64,
    )
    repository = ImportRepository(db_session)
    repository.mark_stage_running(import_id, stage=ImportStage.PARSE)
    db_session.commit()

    worker = ImportWorker(
        session_factory=session_factory, pipeline=RecordingPipeline()
    )
    worker.recover_interrupted()
    db_session.expire_all()

    record = ImportRepository(db_session).get(import_id)
    assert record is not None
    assert record.status is ImportStatus.QUEUED
    parse = record.stage(ImportStage.PARSE)
    assert parse is not None and parse.status is StageStatus.PENDING
