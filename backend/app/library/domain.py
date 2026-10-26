"""Paper library domain: global Paper facts and user-visible entries."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

PDF_MAGIC = b"%PDF-"
TITLE_MAX_LENGTH = 512


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Independent capabilities of a user-visible paper entry."""

    has_source: bool
    has_metadata: bool
    has_parsed: bool
    has_index: bool
    has_embedding: bool


@dataclass(frozen=True, slots=True)
class Paper:
    """A paper with a stored source file; it owns every bibliographic fact."""

    id: UUID
    file_hash: str
    byte_size: int
    page_count: int
    doi: str | None
    arxiv_id: str | None
    bibliographic: dict | None
    metadata_sources: list | None
    mineru_version: str | None
    artifact_manifest_key: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def has_metadata(self) -> bool:
        """Whether bibliographic facts came from a provider, not a placeholder.

        A filename-derived placeholder title is not metadata: without this
        distinction the enrichment stage would never run on an upload.
        """
        return bool(self.metadata_sources) and self.title is not None

    @property
    def was_checked_for_metadata(self) -> bool:
        """Whether a provider was already asked; avoids repeat lookups."""
        return bool(self.metadata_sources)

    @property
    def title(self) -> str | None:
        value = (self.bibliographic or {}).get("title")
        return value if isinstance(value, str) else None

    @property
    def authors(self) -> list[str]:
        value = (self.bibliographic or {}).get("authors")
        return [item for item in value if isinstance(item, str)] if value else []

    @property
    def abstract(self) -> str | None:
        value = (self.bibliographic or {}).get("abstract")
        return value if isinstance(value, str) else None

    @property
    def year(self) -> int | None:
        value = (self.bibliographic or {}).get("year")
        return value if isinstance(value, int) else None

    @property
    def venue(self) -> str | None:
        value = (self.bibliographic or {}).get("venue")
        return value if isinstance(value, str) else None


@dataclass(frozen=True, slots=True)
class UserPaper:
    """Which papers a user keeps; bibliographic facts live on the paper."""

    id: UUID
    user_id: UUID
    paper_id: UUID
    #: Present means usable: entries are written only once a run succeeded.
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def capabilities(
        self,
        paper: Paper | None,
        *,
        has_index: bool = False,
        has_embedding: bool = False,
    ) -> Capabilities:
        """Capabilities for the interface, from the paper and its artifacts.

        ``has_parsed`` reads the published manifest pointer, which the import
        sets only after the parse artifacts are complete. Chunk facts are
        passed in by callers that already queried the chunk table.
        """
        if paper is None:
            return Capabilities(
                has_source=False,
                has_metadata=False,
                has_parsed=False,
                has_index=False,
                has_embedding=False,
            )
        return Capabilities(
            has_source=True,
            has_metadata=paper.has_metadata,
            has_parsed=paper.artifact_manifest_key is not None,
            has_index=has_index,
            has_embedding=has_embedding,
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
    return not (paper.has_parsed and paper.has_index)
