from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from .domain import MetadataStatus, Paper, PaperSource, UserPaper


class PaperRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Global, PDF-identified paper facts shared by every user."""

    __tablename__ = "papers"

    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bibliographic: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    metadata_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MetadataStatus.UNRECOGNIZED.value,
    )
    metadata_sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    has_metadata: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    has_fulltext: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    has_keyword_index: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    has_embedding: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    mineru_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class UserPaperRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user's library entry; stable identity across metadata-only and PDF."""

    __tablename__ = "user_papers"
    # Deliberately no unique constraint on (user_id, paper_id) or identifiers:
    # F09 keeps entry identity stable, so two entries of the same user may point
    # at one shared Paper (for example two PDF versions of the same DOI).
    __table_args__ = (
        Index("ix_user_papers_user_doi", "user_id", "doi"),
        Index("ix_user_papers_user_arxiv", "user_id", "arxiv_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paper_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PaperSource.UPLOAD.value,
    )
    bibliographic: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    metadata_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MetadataStatus.UNRECOGNIZED.value,
    )
    metadata_sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PaperRepository:
    """Persistence for global papers and the user library entries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # Global papers ---------------------------------------------------------
    def get_paper(self, paper_id: UUID) -> Paper | None:
        record = self._session.get(PaperRecord, paper_id)
        return _to_paper(record) if record else None

    def get_paper_by_hash(self, file_hash: str) -> Paper | None:
        record = self._session.scalar(
            select(PaperRecord).where(PaperRecord.file_hash == file_hash),
        )
        return _to_paper(record) if record else None

    def add_paper(
        self,
        *,
        file_hash: str,
        byte_size: int,
        page_count: int,
    ) -> Paper:
        record = PaperRecord(
            file_hash=file_hash,
            byte_size=byte_size,
            page_count=page_count,
            metadata_status=MetadataStatus.UNRECOGNIZED.value,
        )
        self._session.add(record)
        self._session.flush()
        return _to_paper(record)

    def set_paper_capabilities(self, paper_id: UUID, **capabilities: bool) -> None:
        record = self._session.get(PaperRecord, paper_id)
        if record is None:
            return
        for name, value in capabilities.items():
            setattr(record, name, value)
        self._session.flush()

    def set_paper_metadata(
        self,
        paper_id: UUID,
        *,
        bibliographic: dict | None,
        metadata_status: MetadataStatus,
        metadata_sources: list | None,
    ) -> None:
        record = self._session.get(PaperRecord, paper_id)
        if record is None:
            return
        record.bibliographic = bibliographic
        record.metadata_status = metadata_status.value
        record.metadata_sources = metadata_sources
        record.has_metadata = metadata_status in {
            MetadataStatus.RECOGNIZED,
            MetadataStatus.USER_PROVIDED,
        }
        self._session.flush()

    def set_parser_version(self, paper_id: UUID, version: str | None) -> None:
        record = self._session.get(PaperRecord, paper_id)
        if record is None:
            return
        record.mineru_version = version
        self._session.flush()

    def all_paper_ids(self) -> list[UUID]:
        return list(self._session.scalars(select(PaperRecord.id)).all())

    # User entries ----------------------------------------------------------
    def get_user_paper(self, user_paper_id: UUID) -> UserPaper | None:
        record = self._session.get(UserPaperRecord, user_paper_id)
        return _to_user_paper(record) if record else None

    def get_user_paper_for_paper(
        self,
        *,
        user_id: UUID,
        paper_id: UUID,
    ) -> UserPaper | None:
        record = self._session.scalar(
            select(UserPaperRecord).where(
                UserPaperRecord.user_id == user_id,
                UserPaperRecord.paper_id == paper_id,
            ),
        )
        return _to_user_paper(record) if record else None

    def add_user_paper(
        self,
        *,
        user_id: UUID,
        paper_id: UUID | None,
        title: str | None,
        source: PaperSource,
        original_filename: str | None = None,
        doi: str | None = None,
        arxiv_id: str | None = None,
        authors: list[str] | None = None,
        abstract: str | None = None,
        year: int | None = None,
        venue: str | None = None,
        bibliographic: dict | None = None,
        metadata_status: MetadataStatus = MetadataStatus.UNRECOGNIZED,
        metadata_sources: list | None = None,
    ) -> UserPaper:
        record = UserPaperRecord(
            user_id=user_id,
            paper_id=paper_id,
            title=title,
            authors=authors,
            abstract=abstract,
            doi=doi,
            arxiv_id=arxiv_id,
            year=year,
            venue=venue,
            source=source.value,
            bibliographic=bibliographic,
            metadata_status=metadata_status.value,
            metadata_sources=metadata_sources,
            original_filename=original_filename,
        )
        self._session.add(record)
        self._session.flush()
        return _to_user_paper(record)

    def list_user_papers(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[UserPaper], int]:
        statement = select(UserPaperRecord).where(UserPaperRecord.user_id == user_id)
        count_statement = statement.with_only_columns(func.count(UserPaperRecord.id))
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(UserPaperRecord.title.ilike(pattern))
            count_statement = count_statement.where(
                UserPaperRecord.title.ilike(pattern)
            )
        statement = (
            statement.order_by(
                UserPaperRecord.created_at.desc(),
                UserPaperRecord.id,
            )
            .limit(limit)
            .offset(offset)
        )
        records = self._session.scalars(statement).all()
        total = self._session.scalar(count_statement) or 0
        return [_to_user_paper(record) for record in records], int(total)

    def find_user_paper_by_identifier(
        self,
        *,
        user_id: UUID,
        doi: str | None = None,
        arxiv_id: str | None = None,
    ) -> UserPaper | None:
        conditions = []
        if doi:
            conditions.append(UserPaperRecord.doi == doi)
        if arxiv_id:
            conditions.append(UserPaperRecord.arxiv_id == arxiv_id)
        if not conditions:
            return None
        record = self._session.scalar(
            select(UserPaperRecord)
            .where(UserPaperRecord.user_id == user_id)
            .where(or_(*conditions))
            .order_by(UserPaperRecord.created_at),
        )
        return _to_user_paper(record) if record else None

    def user_papers_by_ids(
        self,
        *,
        user_id: UUID,
        user_paper_ids: list[UUID],
    ) -> list[UserPaper]:
        if not user_paper_ids:
            return []
        records = self._session.scalars(
            select(UserPaperRecord).where(
                UserPaperRecord.user_id == user_id,
                UserPaperRecord.id.in_(user_paper_ids),
            ),
        ).all()
        return [_to_user_paper(record) for record in records]

    def entries_for_paper(self, paper_id: UUID) -> list[UserPaper]:
        """Every user entry that currently points at one shared paper."""
        records = self._session.scalars(
            select(UserPaperRecord)
            .where(UserPaperRecord.paper_id == paper_id)
            .order_by(UserPaperRecord.created_at),
        ).all()
        return [_to_user_paper(record) for record in records]

    def paper_scope_for_user(self, user_id: UUID) -> dict[UUID, UUID]:
        """Map shared paper ids to the user's own entry ids (PDF-backed only)."""
        rows = self._session.execute(
            select(UserPaperRecord.paper_id, UserPaperRecord.id)
            .where(
                UserPaperRecord.user_id == user_id,
                UserPaperRecord.paper_id.isnot(None),
            )
            .order_by(UserPaperRecord.created_at),
        ).all()
        scope: dict[UUID, UUID] = {}
        for paper_id, user_paper_id in rows:
            scope.setdefault(paper_id, user_paper_id)
        return scope

    def paper_scope_of_entries(
        self,
        *,
        user_id: UUID,
        user_paper_ids: list[UUID],
    ) -> dict[UUID, UUID]:
        """Map shared paper ids to entry ids for owned, PDF-backed entries."""
        if not user_paper_ids:
            return {}
        rows = self._session.execute(
            select(UserPaperRecord.paper_id, UserPaperRecord.id)
            .where(
                UserPaperRecord.user_id == user_id,
                UserPaperRecord.id.in_(user_paper_ids),
                UserPaperRecord.paper_id.isnot(None),
            )
            .order_by(UserPaperRecord.created_at),
        ).all()
        scope: dict[UUID, UUID] = {}
        for paper_id, user_paper_id in rows:
            scope.setdefault(paper_id, user_paper_id)
        return scope

    def link_user_paper_to_paper(self, user_paper_id: UUID, paper_id: UUID) -> None:
        record = self._session.get(UserPaperRecord, user_paper_id)
        if record is None:
            return
        record.paper_id = paper_id
        self._session.flush()

    def update_user_paper_metadata(
        self,
        user_paper_id: UUID,
        *,
        title: str | None = None,
        authors: list[str] | None = None,
        abstract: str | None = None,
        doi: str | None = None,
        arxiv_id: str | None = None,
        year: int | None = None,
        venue: str | None = None,
        bibliographic: dict | None = None,
        metadata_status: MetadataStatus | None = None,
        metadata_sources: list | None = None,
    ) -> UserPaper | None:
        record = self._session.get(UserPaperRecord, user_paper_id)
        if record is None:
            return None
        if title is not None:
            record.title = title
        if authors is not None:
            record.authors = authors
        if abstract is not None:
            record.abstract = abstract
        if doi is not None:
            record.doi = doi
        if arxiv_id is not None:
            record.arxiv_id = arxiv_id
        if year is not None:
            record.year = year
        if venue is not None:
            record.venue = venue
        if bibliographic is not None:
            record.bibliographic = bibliographic
        if metadata_status is not None:
            record.metadata_status = metadata_status.value
        if metadata_sources is not None:
            record.metadata_sources = metadata_sources
        self._session.flush()
        return _to_user_paper(record)

    def expire_all(self) -> None:
        """Drop cached state so background writes become visible."""
        self._session.expire_all()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def _to_paper(record: PaperRecord) -> Paper:
    return Paper(
        id=record.id,
        file_hash=record.file_hash,
        byte_size=record.byte_size,
        page_count=record.page_count,
        bibliographic=record.bibliographic,
        metadata_status=MetadataStatus(record.metadata_status),
        metadata_sources=record.metadata_sources,
        has_metadata=record.has_metadata,
        has_fulltext=record.has_fulltext,
        has_keyword_index=record.has_keyword_index,
        has_embedding=record.has_embedding,
        mineru_version=record.mineru_version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_user_paper(record: UserPaperRecord) -> UserPaper:
    return UserPaper(
        id=record.id,
        user_id=record.user_id,
        paper_id=record.paper_id,
        title=record.title,
        authors=list(record.authors or []),
        abstract=record.abstract,
        doi=record.doi,
        arxiv_id=record.arxiv_id,
        year=record.year,
        venue=record.venue,
        source=PaperSource(record.source),
        bibliographic=record.bibliographic,
        metadata_status=MetadataStatus(record.metadata_status),
        metadata_sources=record.metadata_sources,
        original_filename=record.original_filename,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
