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
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..platform.database import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from .domain import Paper, PaperSource, UserPaper


class PaperRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Global, PDF-identified paper facts shared by every user."""

    __tablename__ = "papers"

    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    arxiv_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    bibliographic: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    metadata_sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    mineru_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_manifest_key: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserPaperRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user's entry in their library; bibliographic facts live on the paper."""

    __tablename__ = "user_papers"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paper_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PaperSource.UPLOAD.value,
    )
    #: False while the import is still running; the library hides these.
    ready: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )


class PaperRepository:
    """Persistence for global papers and the user library entries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # Global papers ---------------------------------------------------------
    def get_paper(self, paper_id: UUID) -> Paper | None:
        record = self._session.get(PaperRecord, paper_id)
        return _to_paper(record) if record else None

    def link_paper(
        self,
        *,
        user_id: UUID,
        paper_id: UUID,
        source: PaperSource,
    ) -> UserPaper:
        """Record that a user keeps this paper; the entry is not visible yet."""
        existing = self.get_user_paper_for_paper(
            user_id=user_id,
            paper_id=paper_id,
        )
        if existing is not None:
            return existing
        return self.add_user_paper(
            user_id=user_id,
            paper_id=paper_id,
            source=source,
        )

    def mark_entries_ready(self, *, paper_id: UUID) -> int:
        """Reveal every entry waiting on this paper, not just the requester's.

        Several people can be waiting for the same file; each of them gets their
        own entry, and they all become visible together.
        """
        records = self._session.scalars(
            select(UserPaperRecord)
            .where(UserPaperRecord.paper_id == paper_id)
            .where(UserPaperRecord.ready.is_(False)),
        ).all()
        for record in records:
            record.ready = True
        self._session.flush()
        return len(records)

    def get_paper_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """The paper stored for this exact arXiv ID, version included."""
        record = self._session.scalar(
            select(PaperRecord).where(PaperRecord.arxiv_id == arxiv_id).limit(1),
        )
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
        )
        self._session.add(record)
        self._session.flush()
        return _to_paper(record)

    def get_or_add_paper(
        self, *, file_hash: str, byte_size: int, page_count: int
    ) -> Paper:
        self._session.execute(
            pg_insert(PaperRecord)
            .values(
                file_hash=file_hash,
                byte_size=byte_size,
                page_count=page_count,
            )
            .on_conflict_do_nothing(index_elements=[PaperRecord.file_hash])
        )
        paper = self.get_paper_by_hash(file_hash)
        assert paper is not None
        return paper

    def lock_paper(self, paper_id: UUID) -> None:
        self._session.execute(
            select(PaperRecord.id).where(PaperRecord.id == paper_id).with_for_update()
        ).scalar_one_or_none()

    def set_paper_metadata(
        self,
        paper_id: UUID,
        *,
        bibliographic: dict | None,
        metadata_sources: list | None,
        doi: str | None = None,
        arxiv_id: str | None = None,
    ) -> None:
        """Store bibliographic facts; "has metadata" is derived from them."""
        record = self._session.get(PaperRecord, paper_id)
        if record is None:
            return
        record.bibliographic = bibliographic
        record.metadata_sources = metadata_sources
        if doi is not None:
            record.doi = doi
        if arxiv_id is not None:
            record.arxiv_id = arxiv_id
        self._session.flush()

    def set_parser_version(self, paper_id: UUID, version: str | None) -> None:
        record = self._session.get(PaperRecord, paper_id)
        if record is None:
            return
        record.mineru_version = version
        self._session.flush()

    def publish_artifact(
        self, paper_id: UUID, *, manifest_key: str, parser_version: str | None
    ) -> None:
        record = self._session.get(PaperRecord, paper_id)
        if record is None:
            return
        record.artifact_manifest_key = manifest_key
        record.mineru_version = parser_version
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
        paper_id: UUID,
        source: PaperSource,
        ready: bool = False,
    ) -> UserPaper:
        record = UserPaperRecord(
            user_id=user_id,
            paper_id=paper_id,
            source=source.value,
            ready=ready,
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
        statement = (
            select(UserPaperRecord)
            .join(PaperRecord, PaperRecord.id == UserPaperRecord.paper_id)
            .where(UserPaperRecord.user_id == user_id)
            .where(UserPaperRecord.ready.is_(True))
        )
        count_statement = statement.with_only_columns(func.count(UserPaperRecord.id))
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(PaperRecord.bibliographic["title"].astext.ilike(pattern))
            count_statement = count_statement.where(
                PaperRecord.bibliographic["title"].astext.ilike(pattern)
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
        """Find the user's entry for a paper carrying this identifier."""
        conditions = []
        if doi:
            conditions.append(PaperRecord.doi == doi)
        if arxiv_id:
            conditions.append(PaperRecord.arxiv_id == arxiv_id)
        if not conditions:
            return None
        record = self._session.scalar(
            select(UserPaperRecord)
            .join(PaperRecord, PaperRecord.id == UserPaperRecord.paper_id)
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
        return self._paper_scope(user_id=user_id)

    def paper_scope_of_entries(
        self,
        *,
        user_id: UUID,
        user_paper_ids: list[UUID],
    ) -> dict[UUID, UUID]:
        """Map shared paper ids to entry ids for owned, PDF-backed entries."""
        return self._paper_scope(user_id=user_id, user_paper_ids=user_paper_ids)

    def _paper_scope(
        self,
        *,
        user_id: UUID,
        user_paper_ids: list[UUID] | None = None,
    ) -> dict[UUID, UUID]:
        if user_paper_ids is not None and not user_paper_ids:
            return {}
        statement = select(UserPaperRecord.paper_id, UserPaperRecord.id).where(
            UserPaperRecord.user_id == user_id,
            UserPaperRecord.paper_id.isnot(None),
        )
        if user_paper_ids is not None:
            statement = statement.where(UserPaperRecord.id.in_(user_paper_ids))
        rows = self._session.execute(
            statement.order_by(UserPaperRecord.created_at),
        ).all()
        scope: dict[UUID, UUID] = {}
        for paper_id, user_paper_id in rows:
            scope.setdefault(paper_id, user_paper_id)
        return scope

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
        doi=record.doi,
        arxiv_id=record.arxiv_id,
        bibliographic=record.bibliographic,
        metadata_sources=record.metadata_sources,
        mineru_version=record.mineru_version,
        artifact_manifest_key=record.artifact_manifest_key,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_user_paper(record: UserPaperRecord) -> UserPaper:
    return UserPaper(
        id=record.id,
        user_id=record.user_id,
        paper_id=record.paper_id,
        source=PaperSource(record.source),
        ready=record.ready,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
