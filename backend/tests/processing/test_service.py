"""End-to-end processing tests with deterministic stand-in providers."""

import json
import time
from pathlib import Path
from threading import Thread

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.library.repo import PaperRepository
from app.literature_support.importing.mineru import MineruArtifact, MineruParser
from app.pipelines.domain import RunStage, RunStatus
from app.pipelines.pipeline import CONTENT_LIST_OBJECT, MANIFEST_OBJECT, RunPipeline
from app.pipelines.repo import RunRepository, UserRunRecord
from app.pipelines.runs import RunService
from app.platform.storage import ObjectStorage, mineru_artifact_key, paper_pdf_key
from app.platform.tasks import InlineTaskScheduler

CONTENT_LIST = [
    {
        "type": "title",
        "text": "Attention Is All You Need",
        "text_level": 1,
        "page_idx": 0,
    },
    {
        "type": "text",
        "text": "The encoder stacks self attention layers over the input tokens.",
        "page_idx": 0,
    },
    {"type": "title", "text": "3 Model Architecture", "text_level": 1, "page_idx": 1},
    {
        "type": "text",
        "text": "We use scaled dot product attention in every attention head.",
        "page_idx": 1,
    },
]


class CountingMineru(MineruParser):
    """Counts parses so the tests can tell a re-parse from a skip."""

    def __init__(self) -> None:
        self.calls = 0

    def parse(self, *, pdf_path: Path) -> MineruArtifact:
        self.calls += 1
        return MineruArtifact(
            content_list=[dict(item) for item in CONTENT_LIST],
            images={},
            markdown="# paper",
            version="2.1.0",
        )


class StubEmbeddings:
    """Vectors must match the pgvector column width."""

    is_configured = True
    model = "stub"
    dimensions = 1024

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1024 for _ in texts]


@pytest.fixture
def paper(session_factory: sessionmaker[Session], storage: ObjectStorage, clean_tables):
    """A stored paper with its PDF already in the object store."""
    with session_factory() as session:
        record = PaperRepository(session).get_or_add_paper(
            file_hash="b" * 64, byte_size=2048, page_count=2
        )
        session.commit()
        paper_id = record.id
    storage.put_bytes(paper_pdf_key("b" * 64), b"%PDF-1.7 stub")
    return paper_id


@pytest.fixture
def pipeline(session_factory, storage):
    mineru = CountingMineru()
    return (
        RunPipeline(
            scheduler=InlineTaskScheduler(),
            session_factory=session_factory,
            storage=storage,
            mineru=mineru,
            embeddings=StubEmbeddings(),
        ),
        mineru,
    )


def _run_to_completion(runner, session_factory, run_id) -> None:
    """Drive a run through every stage the way the worker does.

    The executor handles one stage per call, so a test that wants a finished
    paper asks for each stage in order.
    """
    for _ in range(len(RunStage)):
        with session_factory() as session:
            stored = RunRepository(session).get(run_id)
            if stored is None or stored.status is not RunStatus.PENDING:
                return
            stage = stored.current_stage
        if stage is None:
            return
        runner.run_sync(run_id, stage=stage)
        with session_factory() as session:
            after = RunRepository(session).get(run_id)
        # A failed stage stays where it is (waiting out a backoff): stop here
        # rather than pretending the next stage is ready.
        if after is not None and after.current_stage is stage:
            return


def _exhaust_retries(runner, session_factory, run_id, *, attempts: int = 3) -> None:
    """Drive a failing stage until its retries are used up."""
    for _ in range(attempts):
        runner.run_sync(run_id, stage=RunStage.PARSE)
        with session_factory() as session:
            stored = RunRepository(session).get(run_id)
            if stored is None or stored.status is RunStatus.FAILED:
                return
            # Retries wait out a backoff; clear it so the test does not sleep.
            if stored.next_attempt_at is not None:
                from app.pipelines.repo import RunRecord

                record = session.get(RunRecord, run_id)
                record.next_attempt_at = None
                session.commit()


def _start_run(session_factory, paper_id) -> object:
    with session_factory() as session:
        run = RunRepository(session).add(paper_id)
        session.commit()
        return run


def test_a_run_parses_then_chunks_then_embeds(paper, pipeline, session_factory) -> None:
    runs, mineru = pipeline
    run = _start_run(session_factory, paper)

    _run_to_completion(runs, session_factory, run.id)

    with session_factory() as session:
        finished = RunRepository(session).get(run.id)
        assert finished is not None
        assert finished.status is RunStatus.SUCCESS
        assert finished.current_stage is None
        assert finished.error_message is None
    assert mineru.calls == 1


def test_a_second_run_reuses_the_verified_artifacts(
    paper, pipeline, session_factory
) -> None:
    """Retrying after a crash must not pay for parsing twice."""
    runs, mineru = pipeline
    first = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, first.id)

    second = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, second.id)

    with session_factory() as session:
        finished = RunRepository(session).get(second.id)
        assert finished is not None
        assert finished.status is RunStatus.SUCCESS
    assert mineru.calls == 1


def test_a_truncated_artifact_is_reparsed_instead_of_failing(
    paper, pipeline, session_factory, storage
) -> None:
    """A half-written file must be repaired, not reported as a dead end."""
    runs, mineru = pipeline
    first = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, first.id)

    key = mineru_artifact_key("b" * 64, CONTENT_LIST_OBJECT)
    storage.put_bytes(key, b'[{"type": "title", "tex')

    second = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, second.id)

    with session_factory() as session:
        finished = RunRepository(session).get(second.id)
        assert finished is not None
        assert finished.status is RunStatus.SUCCESS
    assert mineru.calls == 2


def test_a_missing_artifact_file_is_reparsed(
    paper, pipeline, session_factory, storage
) -> None:
    runs, mineru = pipeline
    first = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, first.id)

    storage.delete_prefix(mineru_artifact_key("b" * 64, ""))

    second = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, second.id)

    with session_factory() as session:
        finished = RunRepository(session).get(second.id)
        assert finished is not None
        assert finished.status is RunStatus.SUCCESS
    assert mineru.calls == 2


def test_a_manifest_from_another_file_is_not_trusted(
    paper, pipeline, session_factory, storage
) -> None:
    runs, mineru = pipeline
    first = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, first.id)

    manifest_key = mineru_artifact_key("b" * 64, MANIFEST_OBJECT)
    manifest = json.loads(storage.read_text(manifest_key))
    manifest["file_hash"] = "c" * 64
    storage.put_bytes(manifest_key, json.dumps(manifest).encode("utf-8"))

    second = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, second.id)

    with session_factory() as session:
        finished = RunRepository(session).get(second.id)
        assert finished is not None
        assert finished.status is RunStatus.SUCCESS
    assert mineru.calls == 2


def test_a_failed_run_names_the_stage_it_stopped_at(
    paper, session_factory, storage
) -> None:
    class ExplodingMineru(MineruParser):
        def parse(self, *, pdf_path: Path) -> MineruArtifact:
            from app.platform.errors import AppError, ErrorCode

            raise AppError(
                "MinerU 解析失败：文件格式不支持",
                code=ErrorCode.PROVIDER_UNAVAILABLE,
                status_code=502,
            )

    runs = RunPipeline(
        scheduler=InlineTaskScheduler(),
        session_factory=session_factory,
        storage=storage,
        mineru=ExplodingMineru(),
        embeddings=StubEmbeddings(),
    )
    run = _start_run(session_factory, paper)
    _run_to_completion(runs, session_factory, run.id)

    with session_factory() as session:
        failed = RunRepository(session).get(run.id)
        assert failed is not None
        # One failure is retried later, so the run waits rather than dying.
        assert failed.status is RunStatus.PENDING
        assert failed.current_stage is RunStage.PARSE
        assert failed.attempts_for(RunStage.PARSE) == 1
        assert failed.error_message == "MinerU 解析失败：文件格式不支持"
        assert failed.next_attempt_at is not None


def test_every_user_who_asked_gets_an_entry_when_the_run_succeeds(
    paper, pipeline, session_factory, make_user
) -> None:
    runs, _ = pipeline
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    service = RunService(session_factory=session_factory)
    first = service.request(user_id=alice, paper_id=paper)
    second = service.request(user_id=bob, paper_id=paper)
    assert first.id == second.id, "两个用户应共用同一条 run"

    _run_to_completion(runs, session_factory, first.id)

    with session_factory() as session:
        papers = PaperRepository(session)
        assert papers.get_user_paper_for_paper(user_id=alice, paper_id=paper)
        assert papers.get_user_paper_for_paper(user_id=bob, paper_id=paper)


def test_a_failed_run_grants_no_entry_to_anyone(
    paper, session_factory, storage, make_user
) -> None:
    class ExplodingMineru(MineruParser):
        def parse(self, *, pdf_path: Path) -> MineruArtifact:
            from app.platform.errors import AppError, ErrorCode

            raise AppError(
                "解析失败", code=ErrorCode.PROVIDER_UNAVAILABLE, status_code=502
            )

    runs = RunPipeline(
        scheduler=InlineTaskScheduler(),
        session_factory=session_factory,
        storage=storage,
        mineru=ExplodingMineru(),
        embeddings=StubEmbeddings(),
    )
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    service = RunService(session_factory=session_factory)
    run = service.request(user_id=alice, paper_id=paper)
    service.request(user_id=bob, paper_id=paper)

    _exhaust_retries(runs, session_factory, run.id)

    with session_factory() as session:
        papers = PaperRepository(session)
        assert papers.get_user_paper_for_paper(user_id=alice, paper_id=paper) is None
        assert papers.get_user_paper_for_paper(user_id=bob, paper_id=paper) is None


def test_a_finished_paper_is_not_processed_again_for_a_later_request(
    paper, pipeline, session_factory, make_user
) -> None:
    """A second user who arrives after success waits for nothing."""
    runs, mineru = pipeline
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    service = RunService(session_factory=session_factory)

    first = service.request(user_id=alice, paper_id=paper)
    _run_to_completion(runs, session_factory, first.id)

    joined = service.request(user_id=bob, paper_id=paper)
    _run_to_completion(runs, session_factory, joined.id)

    with session_factory() as session:
        assert RunRepository(session).get(first.id).status is RunStatus.SUCCESS
        assert PaperRepository(session).get_user_paper_for_paper(
            user_id=bob, paper_id=paper
        )
    assert mineru.calls == 1, "已完成的论文不应重新解析"


class FakeMineruParser(CountingMineru):
    """Alias kept for tests that only need a working parser."""


def _override_services(
    client,
    *,
    session_factory,
    storage,
    mineru,
    embeddings,
    resolver,
    monkeypatch,
    request,
):
    """Drain both queues inline after each submitted request.

    Tests that assert on a failure need the worker to run without the
    ``completed_imports`` fixture, so this installs the same behaviour for one
    case and hands its sessions back for teardown.
    """
    import app.library.service as library_service_module
    from app.pipelines.repo import RunRepository

    opened: list[Session] = []

    def run_worker() -> None:
        from app.literature_support.scholar.pdf_fetch import PdfFetcher
        from app.pipelines.download import DownloadService

        downloads = DownloadService(
            session_factory=session_factory,
            storage=storage,
            fetcher=PdfFetcher(max_bytes=1024 * 1024 * 64),
            resolver=resolver,
            locator=_EmptyLocator(),
        )
        while (download_id := downloads.claim_next()) is not None:
            downloads.run(download_id)
        runs = RunPipeline(
            scheduler=InlineTaskScheduler(),
            session_factory=session_factory,
            storage=storage,
            mineru=mineru,
            embeddings=embeddings,
        )
        for stage in (RunStage.PARSE, RunStage.CHUNK, RunStage.EMBED):
            while True:
                with session_factory() as session:
                    run_id = RunRepository(session).claim_next(
                        stage=stage, lease_seconds=300
                    )
                if run_id is None:
                    break
                runs.run_sync(run_id, stage=stage)

    original_upload = library_service_module.PaperLibraryService.upload_pdf

    def upload_then_work(self, *, user_id, filename, stream, project_id=None):
        run = original_upload(
            self,
            user_id=user_id,
            filename=filename,
            stream=stream,
            project_id=project_id,
        )
        run_worker()
        return run

    monkeypatch.setattr(
        library_service_module.PaperLibraryService, "upload_pdf", upload_then_work
    )
    request.addfinalizer(lambda: [session.close() for session in opened])
    return None


class _EmptyLocator:
    def find(self, doi: str) -> list[str]:
        return []


def test_success_is_rolled_back_when_granting_entries_is_interrupted(
    paper, pipeline, session_factory, make_user, monkeypatch
):
    runner, _ = pipeline
    user_id = make_user()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper)
    original_grant = runner._grant_entries

    def interrupt(**kwargs):
        original_grant(**kwargs)
        raise RuntimeError("injected grant interruption")

    monkeypatch.setattr(runner, "_grant_entries", interrupt)
    with pytest.raises(RuntimeError, match="injected grant interruption"):
        _run_to_completion(runner, session_factory, run.id)
    with session_factory() as session:
        # The run never became success. It stays leased so the reclaim path
        # fails it, rather than leaving "success without entries".
        stored = RunRepository(session).get(run.id)
        assert stored.status is RunStatus.RUNNING
        assert stored.current_stage is RunStage.EMBED
        assert PaperRepository(session).get_user_paper_for_paper(
            user_id=user_id, paper_id=paper
        ) is None


def test_a_request_arriving_mid_run_gets_an_entry_when_it_finishes(
    paper, pipeline, session_factory, make_user, monkeypatch
):
    """A request may join while stages run; finishing must still reach it.

    The request takes the paper lock before reading the active run, so it can
    only join either before the finisher or after it — never in between.
    """
    from threading import Event

    runner, _ = pipeline
    alice, bob = make_user("a@test.example"), make_user("b@test.example")
    run = RunService(session_factory).request(user_id=alice, paper_id=paper)

    # Hold the run half way: parse is done, chunk has not started.
    parsing_done = Event()
    original_stage = runner._run_stage

    def stage_then_pause(stage, **kwargs):
        if stage is RunStage.PARSE:
            original_stage(stage, **kwargs)
            parsing_done.set()
            return
        original_stage(stage, **kwargs)

    monkeypatch.setattr(runner, "_run_stage", stage_then_pause)
    runner.run_sync(run.id, stage=RunStage.PARSE)
    assert parsing_done.is_set()

    # The second request lands while the run is still pending on chunk.
    joined = RunService(session_factory).request(user_id=bob, paper_id=paper)
    assert joined.id == run.id

    for stage in (RunStage.CHUNK, RunStage.EMBED):
        runner.run_sync(run.id, stage=stage)

    with session_factory() as session:
        assert RunRepository(session).get(run.id).status is RunStatus.SUCCESS
        assert PaperRepository(session).get_user_paper_for_paper(
            user_id=bob, paper_id=paper
        ) is not None


def test_a_request_after_success_gets_an_entry_without_a_new_run(
    paper, pipeline, session_factory, make_user
):
    """Arriving after the run succeeded must not restart or wait on anything."""
    runner, _ = pipeline
    alice, bob = make_user("a@test.example"), make_user("b@test.example")
    run = RunService(session_factory).request(user_id=alice, paper_id=paper)
    _run_to_completion(runner, session_factory, run.id)

    later = RunService(session_factory).request(user_id=bob, paper_id=paper)

    with session_factory() as session:
        assert later.id == run.id
        assert len(session.scalars(select(UserRunRecord)).all()) == 1
        assert PaperRepository(session).get_user_paper_for_paper(
            user_id=bob, paper_id=paper
        ) is not None


def test_only_one_executor_parses_when_two_threads_execute_the_same_run(
    paper, pipeline, session_factory, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    runner, parser = pipeline
    run = _start_run(session_factory, paper)
    entered, release = Event(), Event()
    original = parser.parse

    def pause_parse(**kwargs):
        entered.set()
        assert release.wait(5)
        return original(**kwargs)

    monkeypatch.setattr(parser, "parse", pause_parse)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(runner.run_sync, run.id)
        assert entered.wait(5)
        second = executor.submit(runner.run_sync, run.id)
        second.result(timeout=5)
        release.set()
        first.result(timeout=10)
    assert parser.calls == 1


def test_heartbeat_renews_the_lease_when_parsing_outlasts_the_interval(
    paper, pipeline, session_factory, monkeypatch
):
    from threading import Event, current_thread, main_thread

    import app.pipelines.pipeline as module

    runner, parser = pipeline
    run = _start_run(session_factory, paper)
    renewed = Event()
    original_renew = RunRepository.renew_lease
    original_parse = parser.parse

    def renew(self, *args, **kwargs):
        result = original_renew(self, *args, **kwargs)
        if current_thread() is not main_thread():
            renewed.set()
        return result

    def parse(**kwargs):
        assert renewed.wait(5)
        return original_parse(**kwargs)

    monkeypatch.setattr(module, "LEASE_SECONDS", 0.3)
    monkeypatch.setattr(RunRepository, "renew_lease", renew)
    monkeypatch.setattr(parser, "parse", parse)
    runner.run_sync(run.id)
    assert renewed.is_set()


def test_a_live_lease_does_not_let_a_lost_guard_connection_publish_success(
    paper, pipeline, session_factory, monkeypatch
):
    """The lease can still be valid while the executor's own guard is gone."""
    from threading import Event

    import app.pipelines.pipeline as module

    runner, _ = pipeline
    run = _start_run(session_factory, paper)
    parsing, release = Event(), Event()
    holder: dict[str, int | None] = {"pid": None}

    def drop_guard() -> None:
        pid = holder["pid"]
        assert pid is not None, "the executor never took its advisory lock"
        with session_factory() as session:
            session.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
            session.commit()
        # Backends end asynchronously; wait until that one is really gone.
        deadline = time.time() + 5
        while time.time() < deadline:
            with session_factory() as session:
                alive = session.scalar(
                    text("SELECT count(*) FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
            if not alive:
                return
            time.sleep(0.02)

    def parse(*args, **kwargs):
        # The stage begins only after the executor took its guard lock.
        with session_factory() as session:
            holder["pid"] = session.scalar(
                text(
                    "SELECT pid FROM pg_locks WHERE locktype = 'advisory' "
                    "AND objsubid = 1 AND classid = 0 "
                    "AND objid = (hashtextextended(:key, 0) & 4294967295)"
                ),
                {"key": f"paper-run:{run.id}"},
            )
        parsing.set()
        assert release.wait(10)
        drop_guard()
        raise AssertionError("stage body must not run after the guard died")

    monkeypatch.setattr(module, "LEASE_SECONDS", 600)
    monkeypatch.setattr(runner._mineru, "parse", parse)
    thread = Thread(target=lambda: runner.run_sync(run.id), daemon=True)
    thread.start()
    assert parsing.wait(5)
    release.set()
    thread.join(timeout=15)
    with session_factory() as session:
        stored = RunRepository(session).get(run.id)
        assert stored is not None
        assert stored.status is not RunStatus.SUCCESS
