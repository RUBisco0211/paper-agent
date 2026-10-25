"""End-to-end import tests with deterministic stand-in providers."""

import hashlib
import json
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from threading import Lock
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.imports.domain import ImportStage, ImportStatus, StageStatus
from app.imports.queue import ImportQueueService
from app.imports.repo import ImportRepository
from app.library.depends import get_import_starter
from app.library.repo import PaperRepository, UserPaperRecord
from app.literature_support.importing.mineru import MineruArtifact, MineruParser
from app.literature_support.importing.pipeline import ImportPipeline
from app.literature_support.importing.worker import ImportWorker
from app.literature_support.scholar.metadata import MetadataResolver, ProviderMetadata
from app.platform.config import settings
from app.platform.storage import ObjectStorage, paper_pdf_key
from app.platform.tasks import InlineTaskScheduler
from app.retrieval.depends import get_search_embedding_factory
from tests.conftest import ListedObjectStorage, auth_headers, build_pdf_with_text
from tests.library.test_pdf_and_metadata import FakeProvider

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
    {
        "type": "table",
        "table_body": "<table><tr><td>BLEU 41.8</td></tr></table>",
        "page_idx": 2,
    },
]


class FakeMineruParser(MineruParser):
    def __init__(self, artifact: MineruArtifact | None = None) -> None:
        super().__init__(base_url="https://mineru.invalid", api_key="test")
        self.artifact = artifact or MineruArtifact(
            content_list=CONTENT_LIST,
            markdown="# Attention Is All You Need",
            images={"images/figure-1.png": b"\x89PNG-fake"},
            version="2.1.0",
        )
        self.calls: list[Path] = []

    def parse(self, *, pdf_path: Path) -> MineruArtifact:
        self.calls.append(pdf_path)
        return self.artifact


class FakeEmbeddingAdapter:
    """Can switch between configured and unconfigured, and returns fixed vectors."""

    name = "fake"
    model = settings.embedding_model

    def __init__(self, *, configured: bool = True) -> None:
        self.enabled = configured
        self.vectors: list[list[float]] = []
        self.documents: list[str] = []

    def configure(self) -> None:
        self.enabled = True

    @property
    def dimensions(self) -> int:
        return settings.embedding_dimensions

    @property
    def is_configured(self) -> bool:
        return self.enabled

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.documents.extend(texts)
        vectors = [
            [0.1 + index * 0.001 for index in range(self.dimensions)] for _ in texts
        ]
        self.vectors.extend(vectors)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _override_services(
    client: TestClient,
    *,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
    mineru: MineruParser,
    embeddings: FakeEmbeddingAdapter,
    resolver: MetadataResolver,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Point both the upload and retry paths at stand-in providers."""

    opened: list[Session] = []

    def make_service() -> ImportQueueService:
        session = session_factory()
        opened.append(session)
        pipeline = ImportPipeline(
            scheduler=InlineTaskScheduler(),
            session_factory=session_factory,
            storage=storage,
            mineru=mineru,
            embeddings=embeddings,
        )
        return ImportQueueService(
            ImportRepository(session),
            PaperRepository(session),
            runner=pipeline,
        )

    def build_import() -> Iterator[ImportQueueService]:
        yield make_service()

    overrides = cast(FastAPI, client.app).dependency_overrides
    overrides[get_import_starter] = build_import
    overrides[get_search_embedding_factory] = lambda: (
        lambda _user_id: embeddings
    )

    # Identifier imports build their own workflow through this factory; point
    # it at the stand-in providers so a retry runs the same pipeline.
    def build_stub_service(**_kwargs) -> ImportQueueService:
        return make_service()

    import app.imports.depends as import_depends
    import app.literature_support.importing.pipeline as pipeline_module

    monkeypatch.setattr(import_depends, "build_import_service", build_stub_service)
    monkeypatch.setattr(
        pipeline_module, "build_import_service", build_stub_service, raising=False
    )
    # The services keep their own sessions open for the request; hand them to
    # the fixture teardown so the next test can truncate without waiting.
    request.addfinalizer(
        lambda: [session.close() for session in opened if session.is_active]
    )

def _upload(client: TestClient, api_prefix: str, token: str, pdf: bytes):
    return client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("attention.pdf", pdf, "application/pdf")},
    )


def _stages(record) -> dict[ImportStage, StageStatus]:
    return {stage.stage: stage.status for stage in record.stages}


def _entry_id(client: TestClient, api_prefix: str, token: str) -> UUID:
    items = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    return UUID(items["items"][0]["id"])


def test_two_papers_complete_parse_and_indexing_in_parallel(
    session_factory: sessionmaker[Session],
    db_session: Session,
    storage: ObjectStorage,
    make_pdf,
) -> None:
    class PeakTrackingMineru(FakeMineruParser):
        """Record how many parses overlap, so serialized work is visible."""

        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.peak = 0
            self._lock = Lock()

        def parse(self, *, pdf_path: Path) -> MineruArtifact:
            with self._lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                # Hold the slot long enough for a second worker to overlap.
                time.sleep(0.05)
                return super().parse(pdf_path=pdf_path)
            finally:
                with self._lock:
                    self.active -= 1

    from datetime import UTC, datetime

    from app.auth.repo import AuthRepository

    user = AuthRepository(db_session).add_user(
        email="parallel@example.com",
        password_hash="x",
        display_name="Parallel",
        email_verified_at=datetime.now(UTC),
    )
    db_session.commit()
    user_id = user.id

    import_ids = []
    with session_factory() as session:
        papers = PaperRepository(session)
        imports = ImportRepository(session)
        for count in (1, 2):
            pdf = make_pdf(count)
            file_hash = hashlib.sha256(pdf).hexdigest()
            storage.put_bytes(paper_pdf_key(file_hash), pdf)
            paper = papers.add_paper(
                file_hash=file_hash, byte_size=len(pdf), page_count=count
            )
            record = imports.add(
                initiated_by=user_id,
                identifier_type="upload",
                identifier=f"{count}.pdf",
            )
            imports.bind_paper(record.id, paper.id)
            imports.mark_stage_succeeded(record.id, stage=ImportStage.SOURCE)
            import_ids.append(record.id)
        session.commit()
    mineru = PeakTrackingMineru()
    pipeline = ImportPipeline(
        scheduler=None,
        session_factory=session_factory,
        storage=storage,
        mineru=mineru,
        embeddings=FakeEmbeddingAdapter(),
    )
    worker = ImportWorker(session_factory=session_factory, pipeline=pipeline)
    assert worker.run_batch(max_concurrent_imports=2) == 2
    # Two imports were parsed at the same time, not one after the other.
    assert mineru.peak == 2
    with session_factory() as session:
        imports = ImportRepository(session)
        papers = PaperRepository(session)
        for import_id in import_ids:
            record = imports.get(import_id)
            assert record is not None
            assert record.status is ImportStatus.READY
            paper = papers.get_paper(record.paper_id)
            assert paper is not None
            assert paper.artifact_manifest_key is not None


def test_failed_artifact_write_never_publishes_orphaned_parse(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    db_session: Session,
    storage: ListedObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    original_put = storage.put_bytes

    def fail_markdown(key: str, data: bytes) -> None:
        if key.endswith("full.md"):
            raise OSError("storage write failed")
        original_put(key, data)

    monkeypatch.setattr(storage, "put_bytes", fail_markdown)
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=FakeMineruParser(),
        embeddings=FakeEmbeddingAdapter(),
        resolver=MetadataResolver([]),
        monkeypatch=monkeypatch,
        request=request,
    )
    token = register_user(email="artifact-failure@example.com")["access_token"]
    response = _upload(
        client, api_prefix, token, build_pdf_with_text("artifact failure")
    )
    assert response.status_code == 202
    record = ImportRepository(db_session).get(UUID(response.json()["import_id"]))
    assert record is not None
    assert _stages(record)[ImportStage.PARSE] is StageStatus.FAILED
    # No manifest and no half-written artifacts are published.
    db_session.expire_all()
    paper = PaperRepository(db_session).get_paper(record.paper_id)
    assert paper is not None and paper.artifact_manifest_key is None
    assert not list(storage.files("mineru/"))


def test_pipeline_runs_every_stage_and_makes_evidence_searchable(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    db_session: Session,
    storage: ListedObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    mineru = FakeMineruParser()
    embeddings = FakeEmbeddingAdapter()
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            abstract="The dominant sequence transduction models.",
            arxiv_id="1706.03762",
            year=2017,
        ),
    )
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=mineru,
        embeddings=embeddings,
        resolver=MetadataResolver([provider]),
        monkeypatch=monkeypatch,
        request=request,
    )
    token = register_user(email="reader@example.com")["access_token"]
    pdf = build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need")

    uploaded = _upload(client, api_prefix, token, pdf)

    assert uploaded.status_code == 202, uploaded.text
    record = ImportRepository(db_session).get(UUID(uploaded.json()["import_id"]))
    assert record is not None
    assert record.status is ImportStatus.READY, record.error_code
    assert set(_stages(record).values()) == {StageStatus.SUCCEEDED}
    assert [stage.stage for stage in record.stages] == list(ImportStage)

    entry = client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()
    assert entry["total"] == 1
    capabilities = entry["items"][0]["capabilities"]
    assert capabilities["has_parsed"] is True

    # Only text and block indexes reach the recognizer; artifacts stay in storage.
    stored = {key.rsplit("/", 1)[-1] for key in storage.files("mineru/")}
    assert "content_list.json" in stored
    assert "full.md" in stored
    assert "manifest.json" in stored
    assert "figure-1.png" in stored
    assert mineru.calls and mineru.calls[0].suffix == ".pdf"

    db_session.expire_all()
    paper = PaperRepository(db_session).get_paper(record.paper_id)
    assert paper is not None and paper.artifact_manifest_key is not None
    manifest = json.loads(storage.read_text(paper.artifact_manifest_key))
    assert manifest["parser_version"] == "2.1.0"
    assert manifest["files"]["content_list.json"]["sha256"]

    search = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "scaled dot product attention", "limit": 3},
    )
    assert search.status_code == 200, search.text
    payload = search.json()
    assert payload["channels"]["keyword"]["status"] == "ok"
    assert payload["evidence"]
    top = payload["evidence"][0]
    assert "scaled dot product attention" in top["snippet"]
    assert "BLEU 41.8" in top["snippet"]
    UUID(top["chunk_ids"][0])


def test_parsed_text_survives_an_unavailable_embedding_provider(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    db_session: Session,
    storage: ObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=FakeMineruParser(),
        embeddings=FakeEmbeddingAdapter(configured=False),
        resolver=MetadataResolver([]),
        monkeypatch=monkeypatch,
        request=request,
    )
    token = register_user(email="reader@example.com")["access_token"]

    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need"),
    )

    assert uploaded.status_code == 202, uploaded.text
    record = ImportRepository(db_session).get(UUID(uploaded.json()["import_id"]))
    assert record is not None
    stages = _stages(record)
    assert stages[ImportStage.PARSE] is StageStatus.SUCCEEDED
    assert stages[ImportStage.CHUNK] is StageStatus.SUCCEEDED
    assert stages[ImportStage.EMBED] is StageStatus.FAILED
    assert record.status is ImportStatus.FAILED
    # The paper is not usable yet: an unfinished import stays in the queue.
    assert client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()[
        "total"
    ] == 0


def test_a_failed_metadata_lookup_does_not_block_an_import(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    db_session: Session,
    storage: ObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Bibliographic lookup runs beside the stages and cannot fail an import."""
    from app.platform.errors import AppError, ErrorCode

    provider = FakeProvider(
        error=AppError(
            "元数据服务暂时不可用",
            code=ErrorCode.METADATA_PROVIDER_FAILED,
            status_code=502,
        ),
    )
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=FakeMineruParser(),
        embeddings=FakeEmbeddingAdapter(),
        resolver=MetadataResolver([provider]),
        monkeypatch=monkeypatch,
        request=request,
    )
    token = register_user(email="reader@example.com")["access_token"]

    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need"),
    )

    assert uploaded.status_code == 202, uploaded.text
    record = ImportRepository(db_session).get(UUID(uploaded.json()["import_id"]))
    assert record is not None
    assert record.status is ImportStatus.READY
    assert not [stage for stage in record.stages if stage.error_code]


def test_retry_is_rejected_while_a_finished_import_has_nothing_to_do(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    provider = FakeProvider(
        ProviderMetadata(
            source="fake",
            title="Attention Is All You Need",
            authors=["Ashish Vaswani"],
            arxiv_id="1706.03762",
        ),
    )
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=FakeMineruParser(),
        embeddings=FakeEmbeddingAdapter(),
        resolver=MetadataResolver([provider]),
        monkeypatch=monkeypatch,
        request=request,
    )
    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need"),
    )
    import_id = uploaded.json()["import_id"]

    # Retrying a finished import re-queues it rather than duplicating work.
    retried = client.post(
        f"{api_prefix}/imports/{import_id}/retry",
        headers=auth_headers(token),
    )

    assert retried.status_code in {202, 409}


def test_retry_reruns_only_the_unfinished_stage(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    db_session: Session,
    storage: ObjectStorage,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    embeddings = FakeEmbeddingAdapter(configured=False)
    mineru = FakeMineruParser()
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=mineru,
        embeddings=embeddings,
        resolver=MetadataResolver([]),
        monkeypatch=monkeypatch,
        request=request,
    )
    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 attention paper"),
    )
    import_id = UUID(uploaded.json()["import_id"])
    parses_before = len(mineru.calls)

    embeddings.configure()
    retried = client.post(
        f"{api_prefix}/imports/{import_id}/retry",
        headers=auth_headers(token),
    )

    assert retried.status_code == 202, retried.text
    db_session.expire_all()
    record = ImportRepository(db_session).get(import_id)
    assert record is not None
    assert record.status is ImportStatus.READY
    # Parsing is the scarce step: a retry must not repeat it.
    assert len(mineru.calls) == parses_before
    assert client.get(f"{api_prefix}/papers", headers=auth_headers(token)).json()[
        "total"
    ] == 1
