"""Paper library domain: global Paper facts and user-visible entries."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

PDF_MAGIC = b"%PDF-"
TITLE_MAX_LENGTH = 512


class PaperSource(StrEnum):
    UPLOAD = "upload"
    DOI = "doi"
    ARXIV = "arxiv"
    MANUAL = "manual"


class MetadataStatus(StrEnum):
    """How complete the bibliographic record currently is."""

    RECOGNIZED = "recognized"
    PARTIAL = "partial"
    UNRECOGNIZED = "unrecognized"
    PROVIDER_FAILED = "provider_failed"
    USER_PROVIDED = "user_provided"


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Independent capabilities of a user-visible paper entry."""

    has_pdf: bool
    has_metadata: bool
    has_fulltext: bool
    has_keyword_index: bool
    has_embedding: bool


@dataclass(frozen=True, slots=True)
class Paper:
    """A PDF-identified paper; it carries shared parsing facts."""

    id: UUID
    file_hash: str
    byte_size: int
    page_count: int
    bibliographic: dict | None
    metadata_status: MetadataStatus
    metadata_sources: list | None
    has_metadata: bool
    has_fulltext: bool
    has_keyword_index: bool
    has_embedding: bool
    mineru_version: str | None
    artifact_manifest_key: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UserPaper:
    """A user's library entry; its identity survives gaining a PDF."""

    id: UUID
    user_id: UUID
    paper_id: UUID | None
    title: str | None
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    venue: str | None = None
    source: PaperSource = PaperSource.UPLOAD
    bibliographic: dict | None = None
    metadata_status: MetadataStatus = MetadataStatus.UNRECOGNIZED
    metadata_sources: list | None = None
    original_filename: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def capabilities(self, paper: Paper | None) -> Capabilities:
        if paper is None:
            return Capabilities(
                has_pdf=False,
                has_metadata=False,
                has_fulltext=False,
                has_keyword_index=False,
                has_embedding=False,
            )
        return Capabilities(
            has_pdf=True,
            has_metadata=paper.has_metadata,
            has_fulltext=paper.has_fulltext,
            has_keyword_index=paper.has_keyword_index,
            has_embedding=paper.has_embedding,
        )


def placeholder_title_from_filename(filename: str | None) -> str | None:
    """Derive a readable placeholder title from an uploaded file name."""
    if not filename:
        return None
    stem = filename.rsplit("/", 1)[-1]
    for suffix in (".pdf", ".PDF"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    stem = stem.replace("_", " ").replace("-", " ").strip()
    if not stem:
        return None
    return stem[:TITLE_MAX_LENGTH]


def paper_needs_processing(paper: Paper) -> bool:
    """Whether a newly linked PDF still has stages left to run."""
    return not (paper.has_fulltext and paper.has_keyword_index)
