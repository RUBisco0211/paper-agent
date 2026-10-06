from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.domain import IngestionStage, IngestionStatus, StageStatus
from app.ingestion.repo import (
    IngestionJobRecord,
    IngestionRepository,
    IngestionStageRecordOrm,
)
from app.library.repo import UserPaperRecord
from app.platform.tasks import ApiTaskScheduler
from app.processing.worker import IngestionWorker


class RecordingPipeline:
    def __init__(self) -> None:
        self.jobs: list[UUID] = []

    def run_sync(self, job_id: UUID) -> None:
        self.jobs.append(job_id)


def test_api_scheduler_leaves_parsing_to_the_worker_when_jobs_are_submitted() -> None:
    submitted: list[str] = []

    class RecordingScheduler:
        def submit(self, factory, *, name: str) -> None:
            submitted.append(name)

    scheduler = ApiTaskScheduler(RecordingScheduler())
    scheduler.submit(lambda: None, name="ingestion:one")
    scheduler.submit(lambda: None, name="import:two")

    assert submitted == ["import:two"]


def test_worker_claims_a_queued_job_when_the_api_has_only_persisted_it(
    session_factory: sessionmaker[Session],
    db_session: Session,
    register_user,
    client,
    api_prefix,
    make_pdf,
) -> None:
    token = register_user(email="worker@example.com")["access_token"]
    uploaded = client.post(
        f"{api_prefix}/papers",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("worker.pdf", make_pdf(), "application/pdf")},
    )
    paper_id = db_session.get(
        UserPaperRecord, UUID(uploaded.json()["paper"]["id"])
    ).paper_id
    queued = IngestionRepository(db_session).create_job(
        paper_id=paper_id, stages=(IngestionStage.FULLTEXT,)
    )
    db_session.commit()
    pipeline = RecordingPipeline()

    worker = IngestionWorker(session_factory=session_factory, pipeline=pipeline)

    assert worker.run_once() is True
    assert pipeline.jobs == [queued.id]


def test_worker_requeues_an_interrupted_stage_when_it_restarts(
    session_factory: sessionmaker[Session],
    db_session: Session,
    register_user,
    client,
    api_prefix,
    make_pdf,
) -> None:
    token = register_user(email="restart@example.com")["access_token"]
    uploaded = client.post(
        f"{api_prefix}/papers",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("restart.pdf", make_pdf(), "application/pdf")},
    )
    paper_id = db_session.get(
        UserPaperRecord, UUID(uploaded.json()["paper"]["id"])
    ).paper_id
    repo = IngestionRepository(db_session)
    job = repo.create_job(paper_id=paper_id, stages=(IngestionStage.FULLTEXT,))
    repo.mark_running(job.id, stage=IngestionStage.FULLTEXT)
    db_session.commit()

    worker = IngestionWorker(
        session_factory=session_factory, pipeline=RecordingPipeline()
    )
    worker.recover_interrupted()
    db_session.expire_all()

    assert (
        db_session.get(IngestionJobRecord, job.id).status
        == IngestionStatus.QUEUED.value
    )
    stage = (
        db_session.query(IngestionStageRecordOrm)
        .filter_by(ingestion_job_id=job.id)
        .one()
    )
    assert stage.status == StageStatus.PENDING.value
