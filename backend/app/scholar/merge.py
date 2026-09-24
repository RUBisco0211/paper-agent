"""Field-level merge rules for provider metadata.

One rule is shared by every path that writes bibliographic data: a field the
user corrected is never overwritten, and an exact identifier lookup replaces a
placeholder. Keeping it here avoids two divergent implementations.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from ..library.domain import UserPaper
from .metadata import ProviderMetadata


@dataclass(frozen=True, slots=True)
class MergedMetadata:
    title: str | None = None
    authors: list[str] | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    venue: str | None = None
    applied_fields: tuple[str, ...] = ()

    def changes_anything(self) -> bool:
        return bool(self.applied_fields)


def user_overridden_fields(sources: list | None) -> set[str]:
    return {
        str(entry.get("field"))
        for entry in (sources or [])
        if entry.get("source") == "user"
    }


def merge_provider_metadata(
    current: UserPaper,
    metadata: ProviderMetadata,
) -> MergedMetadata:
    """Merge provider fields into one entry, preserving user corrections."""
    overridden = user_overridden_fields(current.metadata_sources)
    applied: list[str] = []

    def _merge(field: str, existing, provided):
        if field in overridden or provided in (None, "", []):
            return existing
        if provided != existing:
            applied.append(field)
        return provided

    return MergedMetadata(
        title=_merge("title", current.title, metadata.title),
        authors=_merge("authors", current.authors, metadata.authors),
        abstract=_merge("abstract", current.abstract, metadata.abstract),
        doi=_merge("doi", current.doi, metadata.doi),
        arxiv_id=_merge("arxiv_id", current.arxiv_id, metadata.arxiv_id),
        year=_merge("year", current.year, metadata.year),
        venue=_merge("venue", current.venue, metadata.venue),
        applied_fields=tuple(applied),
    )


def merge_sources(
    existing: list | None,
    fields: list[str],
    *,
    source: str = "user",
) -> list:
    """Record where each field came from, replacing older entries per field."""
    replaced = set(fields)
    now = datetime.now(UTC).isoformat()
    kept = [entry for entry in (existing or []) if entry.get("field") not in replaced]
    return [
        *kept,
        *({"field": field, "source": source, "at": now} for field in fields),
    ]
