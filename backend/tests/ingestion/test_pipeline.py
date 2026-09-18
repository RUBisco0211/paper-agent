"""End-to-end pipeline tests with deterministic stand-in providers."""

from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.application import IngestionService
from app.ingestion.dependencies import get_ingestion_service
from app.ingestion.mineru import MineruArtifact, MineruParser
from app.ingestion.persistence import IngestionRepository
from app.ingestion.pipeline import IngestionPipeline
from app.library.dependencies import get_ingestion_starter
from app.library.persistence import PaperRepository
from app.platform.config import settings
from app.platform.storage import ObjectStorage
from app.platform.tasks import InlineTaskScheduler
from app.retrieval.dependencies import get_embedding_adapter
from app.scholar.metadata import MetadataResolver, ProviderMetadata
from tests.conftest import auth_headers, build_pdf_with_text
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
    """实现 EmbeddingAdapter：可切换"已配置/未配置"，返回固定维度向量。"""

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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
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
    session_factory: Callable[[], Session],
    storage: ObjectStorage,
    mineru: MineruParser,
    embeddings: FakeEmbeddingAdapter,
    resolver: MetadataResolver,
) -> None:
    storage = storage

    def build_ingestion() -> Iterator[IngestionService]:
        session = session_factory()
        try:
            papers = PaperRepository(session)
            pipeline = IngestionPipeline(
                scheduler=InlineTaskScheduler(),
                session_factory=session_factory,
                storage=storage,
                mineru=mineru,
                resolver=resolver,
                embeddings=embeddings,
            )
            yield IngestionService(
                IngestionRepository(session),
                papers,
                runner=pipeline,
            )
        finally:
            session.close()

    # Both the upload path (library) and the retry path (ingestion API) must
    # use the same stand-in providers.
    client.app.dependency_overrides[get_ingestion_starter] = build_ingestion
    client.app.dependency_overrides[get_ingestion_service] = build_ingestion
    client.app.dependency_overrides[get_embedding_adapter] = lambda: embeddings


def _upload(client: TestClient, api_prefix: str, token: str, pdf: bytes):
    return client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(token),
        files={"file": ("attention.pdf", pdf, "application/pdf")},
    )


def test_pipeline_runs_every_stage_and_makes_evidence_searchable(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
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
    )
    token = register_user(email="reader@example.com")["access_token"]
    pdf = build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need")

    uploaded = _upload(client, api_prefix, token, pdf)

    assert uploaded.status_code == 202, uploaded.text
    body = uploaded.json()
    paper_id = body["paper"]["id"]
    assert body["paper"]["capabilities"] == {
        "has_pdf": True,
        "has_metadata": True,
        "has_fulltext": True,
        "has_keyword_index": True,
        "has_embedding": True,
    }
    job = body["ingestion_job"]
    assert job["status"] == "succeeded"
    assert job["error_code"] is None
    stages = {stage["stage"]: stage["status"] for stage in job["stages"]}
    assert stages == {
        "metadata": "succeeded",
        "fulltext": "succeeded",
        "chunking": "succeeded",
        "embedding": "succeeded",
    }

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()
    assert detail["title"] == "Attention Is All You Need"
    assert detail["metadata_status"] == "recognized"
    assert detail["capabilities"]["has_fulltext"] is True

    # Only paper text and block indexes were sent to the recognizer; the
    # original PDF and MinerU artifacts stay in object storage.
    stored = {key.rsplit("/", 1)[-1] for key in storage.files("mineru/")}
    assert "content_list.json" in stored
    assert "full.md" in stored
    assert "figure-1.png" in stored
    assert mineru.calls and mineru.calls[0].suffix == ".pdf"

    search = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "scaled dot product attention", "limit": 3},
    )
    assert search.status_code == 200, search.text
    payload = search.json()
    assert payload["status"] == "ok"
    assert payload["channels"]["keyword"]["status"] == "ok"
    assert payload["channels"]["vector"]["status"] == "ok"
    assert payload["evidence"]
    top = payload["evidence"][0]
    assert top["paper_id"] == paper_id
    # The blocks of this short paper fit one chunk spanning pages 1-3.
    assert top["page_start"] == 1
    assert top["page_end"] == 3
    assert "scaled dot product attention" in top["snippet"]
    assert "BLEU 41.8" in top["snippet"]
    UUID(top["chunk_ids"][0])


def test_fulltext_survives_an_unavailable_embedding_provider(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
) -> None:
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=FakeMineruParser(),
        embeddings=FakeEmbeddingAdapter(configured=False),
        resolver=MetadataResolver([]),
    )
    token = register_user(email="reader@example.com")["access_token"]

    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need"),
    )

    assert uploaded.status_code == 202, uploaded.text
    body = uploaded.json()
    capabilities = body["paper"]["capabilities"]
    assert capabilities["has_fulltext"] is True
    assert capabilities["has_keyword_index"] is True
    assert capabilities["has_embedding"] is False
    stages = {stage["stage"]: stage for stage in body["ingestion_job"]["stages"]}
    assert stages["fulltext"]["status"] == "succeeded"
    assert stages["chunking"]["status"] == "succeeded"
    assert stages["embedding"]["status"] == "failed"
    assert stages["embedding"]["error_code"] == "provider_not_configured"
    assert body["ingestion_job"]["status"] == "failed"

    search = client.post(
        f"{api_prefix}/search",
        headers=auth_headers(token),
        json={"query": "scaled dot product attention"},
    )
    payload = search.json()
    assert payload["channels"]["keyword"]["status"] == "ok"
    assert payload["channels"]["vector"]["status"] == "skipped"
    assert payload["status"] == "degraded"
    assert payload["evidence"]


def test_metadata_failure_does_not_block_fulltext(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
) -> None:
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
    )
    token = register_user(email="reader@example.com")["access_token"]

    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need"),
    )

    assert uploaded.status_code == 202, uploaded.text
    body = uploaded.json()
    stages = {stage["stage"]: stage for stage in body["ingestion_job"]["stages"]}
    assert stages["metadata"]["status"] == "failed"
    assert stages["metadata"]["error_code"] == "metadata_provider_failed"
    # Non-blocking: the body is still parsed and indexed.
    assert stages["fulltext"]["status"] == "succeeded"
    assert stages["chunking"]["status"] == "succeeded"
    assert body["paper"]["capabilities"]["has_fulltext"] is True
    assert body["paper"]["capabilities"]["has_metadata"] is False


def test_retry_after_a_successful_run_is_rejected(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
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
    )
    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 Attention Is All You Need"),
    )
    job_id = uploaded.json()["ingestion_job"]["id"]
    assert uploaded.json()["ingestion_job"]["status"] == "succeeded"

    response = client.post(
        f"{api_prefix}/ingestion-jobs/{job_id}/retry",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ingestion_nothing_to_retry"


def test_reindexing_after_a_failed_embedding_stage_keeps_chunks(
    client: TestClient,
    api_prefix: str,
    register_user,
    session_factory: sessionmaker[Session],
    storage: ObjectStorage,
) -> None:
    embeddings = FakeEmbeddingAdapter(configured=False)
    _override_services(
        client,
        session_factory=session_factory,
        storage=storage,
        mineru=FakeMineruParser(),
        embeddings=embeddings,
        resolver=MetadataResolver([]),
    )
    token = register_user(email="reader@example.com")["access_token"]
    uploaded = _upload(
        client,
        api_prefix,
        token,
        build_pdf_with_text("arXiv:1706.03762 attention paper"),
    )
    job_id = uploaded.json()["ingestion_job"]["id"]
    paper_id = UUID(uploaded.json()["paper"]["id"])

    # The embedding provider comes back; only the missing stage must redo work.
    embeddings.configure()
    retried = client.post(
        f"{api_prefix}/ingestion-jobs/{job_id}/retry",
        headers=auth_headers(token),
    )

    assert retried.status_code == 202, retried.text
    body = retried.json()
    stages = {stage["stage"]: stage["status"] for stage in body["stages"]}
    # Only the missing embedding work is redone; verified stages are skipped.
    assert stages == {
        "metadata": "succeeded",
        "fulltext": "skipped",
        "chunking": "skipped",
        "embedding": "succeeded",
    }
    assert body["status"] == "succeeded"

    detail = client.get(
        f"{api_prefix}/papers/{paper_id}",
        headers=auth_headers(token),
    ).json()
    assert detail["capabilities"]["has_embedding"] is True
