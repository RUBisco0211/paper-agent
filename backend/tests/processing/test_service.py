"""End-to-end processing tests with deterministic stand-in providers."""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.library.repo import PaperRepository
from app.literature_support.importing.mineru import MineruArtifact, MineruParser
from app.pipelines.domain import RunStage, RunStatus
from app.pipelines.pipeline import CONTENT_LIST_OBJECT, MANIFEST_OBJECT, RunPipeline
from app.pipelines.repo import RunRepository
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


def _start_run(session_factory, paper_id) -> object:
    with session_factory() as session:
        run = RunRepository(session).add(paper_id)
        session.commit()
        return run


def test_a_run_parses_then_chunks_then_embeds(paper, pipeline, session_factory) -> None:
    runs, mineru = pipeline
    run = _start_run(session_factory, paper)

    runs.run_sync(run.id)

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
    runs.run_sync(first.id)

    second = _start_run(session_factory, paper)
    runs.run_sync(second.id)

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
    runs.run_sync(first.id)

    key = mineru_artifact_key("b" * 64, CONTENT_LIST_OBJECT)
    storage.put_bytes(key, b'[{"type": "title", "tex')

    second = _start_run(session_factory, paper)
    runs.run_sync(second.id)

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
    runs.run_sync(first.id)

    storage.delete_prefix(mineru_artifact_key("b" * 64, ""))

    second = _start_run(session_factory, paper)
    runs.run_sync(second.id)

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
    runs.run_sync(first.id)

    manifest_key = mineru_artifact_key("b" * 64, MANIFEST_OBJECT)
    manifest = json.loads(storage.read_text(manifest_key))
    manifest["file_hash"] = "c" * 64
    storage.put_bytes(manifest_key, json.dumps(manifest).encode("utf-8"))

    second = _start_run(session_factory, paper)
    runs.run_sync(second.id)

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
    runs.run_sync(run.id)

    with session_factory() as session:
        failed = RunRepository(session).get(run.id)
        assert failed is not None
        assert failed.status is RunStatus.FAILED
        assert failed.current_stage is RunStage.PARSE
        assert failed.error_message == "MinerU 解析失败：文件格式不支持"


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

    runs.run_sync(first.id)

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

    runs.run_sync(run.id)

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
    runs.run_sync(first.id)

    joined = service.request(user_id=bob, paper_id=paper)
    runs.run_sync(joined.id)

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
        while True:
            with session_factory() as session:
                run_id = RunRepository(session).claim_next(lease_seconds=300)
            if run_id is None:
                break
            runs.run_sync(run_id)

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
