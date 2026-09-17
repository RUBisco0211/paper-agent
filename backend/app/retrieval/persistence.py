"""Chunk persistence with PostgreSQL full-text and pgvector recall."""

from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.config import settings
from ..platform.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .domain import Chunk, ChunkDraft, ChunkMatch

FTS_CONFIGURATION = "english"


class ChunkRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("paper_id", "chunk_index", name="uq_chunk_index"),
        Index(
            "ix_chunks_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    chunk_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title_path, '') || ' ' || content)",
            persisted=True,
        ),
        nullable=False,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimensions),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)


def chunk_embedding_dimension(session: Session) -> int | None:
    """读取 ``chunks.embedding`` 的实际维度，用于启动自检。

    换模型时最容易踩的坑是「配置维度改了、迁移没做」：写入会在数据库层失败。
    这里把两边的值拿出来比较，失败时给一条明确的日志。
    """
    row = session.execute(
        text(
            "SELECT format_type(atttypid, atttypmod) "
            "FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'",
        ),
    ).scalar()
    if not row or "(" not in str(row):
        return None
    try:
        return int(str(row).split("(")[1].rstrip(")"))
    except ValueError:
        return None


class ChunkRepository:
    """Stores chunk-level evidence and runs the two recall channels."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_chunks(self, *, paper_id: UUID, drafts: list[ChunkDraft]) -> int:
        """Idempotently rewrite a paper's chunks.

        Re-running chunking must not duplicate evidence, so existing rows for
        the paper are removed inside the same transaction.
        """
        self.delete_chunks(paper_id)
        for draft in drafts:
            self._session.add(
                ChunkRecord(
                    paper_id=paper_id,
                    chunk_index=draft.chunk_index,
                    title_path=draft.title_path,
                    content=draft.content,
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    block_ids=draft.block_ids,
                    chunk_metadata=draft.chunk_metadata,
                ),
            )
        self._session.flush()
        return len(drafts)

    def delete_chunks(self, paper_id: UUID) -> int:
        records = self._session.scalars(
            select(ChunkRecord).where(ChunkRecord.paper_id == paper_id),
        ).all()
        for record in records:
            self._session.delete(record)
        self._session.flush()
        return len(records)

    def count_chunks(self, paper_id: UUID) -> int:
        return (
            self._session.scalar(
                select(func.count(ChunkRecord.id)).where(
                    ChunkRecord.paper_id == paper_id,
                ),
            )
            or 0
        )

    def pending_embedding_chunks(
        self,
        paper_id: UUID,
        *,
        limit: int | None = None,
    ) -> list[Chunk]:
        statement = (
            select(ChunkRecord)
            .where(
                ChunkRecord.paper_id == paper_id,
                ChunkRecord.embedding.is_(None),
            )
            .order_by(ChunkRecord.chunk_index)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return [_to_chunk(record) for record in self._session.scalars(statement).all()]

    def set_embedding(
        self,
        *,
        chunk_id: UUID,
        embedding: list[float],
        model: str,
    ) -> None:
        record = self._session.get(ChunkRecord, chunk_id)
        if record is None:
            return
        record.embedding = embedding
        record.embedding_model = model
        record.embedding_dimensions = len(embedding)
        self._session.flush()

    def chunks_by_ids(self, chunk_ids: list[UUID]) -> dict[UUID, Chunk]:
        if not chunk_ids:
            return {}
        records = self._session.scalars(
            select(ChunkRecord).where(ChunkRecord.id.in_(chunk_ids)),
        ).all()
        return {record.id: _to_chunk(record) for record in records}

    def search_keyword(
        self,
        *,
        paper_ids: list[UUID],
        query: str,
        limit: int,
    ) -> list[ChunkMatch]:
        if not paper_ids or not query.strip():
            return []
        tsquery = func.plainto_tsquery(FTS_CONFIGURATION, query)
        statement = (
            select(
                ChunkRecord,
                func.ts_rank(ChunkRecord.search_vector, tsquery).label("score"),
            )
            .where(
                ChunkRecord.paper_id.in_(paper_ids),
                ChunkRecord.search_vector.op("@@")(tsquery),
            )
            .order_by(func.ts_rank(ChunkRecord.search_vector, tsquery).desc())
            .limit(limit)
        )
        rows = self._session.execute(statement).all()
        return [
            ChunkMatch(
                chunk=_to_chunk(record),
                score=float(score),
                rank=rank,
                channel="keyword",
            )
            for rank, (record, score) in enumerate(rows, start=1)
        ]

    def search_vector(
        self,
        *,
        paper_ids: list[UUID],
        embedding: list[float],
        model: str,
        limit: int,
    ) -> list[ChunkMatch]:
        if not paper_ids:
            return []
        distance = ChunkRecord.embedding.cosine_distance(embedding)
        statement = (
            select(ChunkRecord, distance.label("distance"))
            .where(
                ChunkRecord.paper_id.in_(paper_ids),
                ChunkRecord.embedding.isnot(None),
                ChunkRecord.embedding_model == model,
            )
            .order_by(distance)
            .limit(limit)
        )
        rows = self._session.execute(statement).all()
        return [
            ChunkMatch(
                chunk=_to_chunk(record),
                score=1.0 - float(distance),
                rank=rank,
                channel="vector",
            )
            for rank, (record, distance) in enumerate(rows, start=1)
        ]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def _to_chunk(record: ChunkRecord) -> Chunk:
    return Chunk(
        id=record.id,
        paper_id=record.paper_id,
        chunk_index=record.chunk_index,
        title_path=record.title_path,
        content=record.content,
        page_start=record.page_start,
        page_end=record.page_end,
        block_ids=record.block_ids,
        chunk_metadata=record.chunk_metadata,
        embedding_model=record.embedding_model,
        embedding_dimensions=record.embedding_dimensions,
        created_at=record.created_at,
    )
