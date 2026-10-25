"""Resolve a stored source file into bibliographic facts.

Bibliographic lookup depends only on the source file, never on parsing, so it
runs beside the processing pipeline instead of queueing inside it. A failure is
recorded on the paper and never blocks parsing, chunking or embedding.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog

from app.library.domain import MetadataStatus
from app.library.repo import PaperRepository
from app.literature_support.importing.text import detect_identifiers
from app.literature_support.scholar.identifiers import Identifier, IdentifierType
from app.literature_support.scholar.metadata import MetadataResolver
from app.platform.errors import AppError
from app.platform.storage import ObjectStorage, paper_pdf_key

logger = structlog.get_logger(__name__)


def preferred_identifier(identifiers: list[Identifier]) -> Identifier:
    """Prefer DOI over arXiv when a file carries both."""
    for identifier in identifiers:
        if identifier.type is IdentifierType.DOI:
            return identifier
    return identifiers[0]


def source_entry(identifier: Identifier, source: str | None) -> dict:
    return {
        "field": identifier.type.value,
        "value": identifier.full_value,
        "source": source or "local_recognition",
        "at": datetime.now(UTC).isoformat(),
    }


#: Bibliographic lookups are network calls to third-party providers. Two at a
#: time keeps a batch upload from flooding them, and nothing waits on the result.
MAX_CONCURRENT_LOOKUPS = 2

#: One pool per process: creating a pool per request would leak a thread each
#: time, and the limit is a property of the provider, not of a request.
_POOL: ThreadPoolExecutor | None = None
_POOL_LOCK = threading.Lock()


def shared_pool() -> ThreadPoolExecutor:
    """One pool per process, holding at most a couple of provider calls."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(
                max_workers=MAX_CONCURRENT_LOOKUPS,
                thread_name_prefix="metadata",
            )
        return _POOL


def shutdown_pool(wait: bool = True) -> None:
    """Stop the shared pool; used on shutdown and by tests between cases."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            _POOL.shutdown(wait=wait)
            _POOL = None


class MetadataEnricher:
    """Fill a paper's bibliographic facts from its own source file."""

    def __init__(
        self,
        *,
        storage: ObjectStorage,
        resolver: MetadataResolver,
        session_factory,
        papers: PaperRepository | None = None,
    ) -> None:
        self._storage = storage
        self._resolver = resolver
        self._session_factory = session_factory
        self._papers = papers

    def submit(self, paper_id: UUID) -> None:
        """Queue the lookup without making the caller wait for the network."""
        shared_pool().submit(self._run_isolated, paper_id)

    def _run_isolated(self, paper_id: UUID) -> None:
        """Run in its own session so a shared one is never touched."""
        session = self._session_factory()
        try:
            enricher = MetadataEnricher(
                storage=self._storage,
                resolver=self._resolver,
                session_factory=self._session_factory,
                papers=PaperRepository(session),
            )
            enricher.enrich(paper_id)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning(
                "metadata.lookup_failed",
                paper_id=str(paper_id),
                error_type=type(exc).__name__,
            )
        finally:
            session.close()

    def enrich(self, paper_id: UUID) -> MetadataStatus:
        """Recognize identifiers in the file, then resolve them online.

        Returns the resulting status; it is persisted either way so a repeat
        call does not query the network again for a settled answer.
        """
        paper = self._papers.get_paper(paper_id)
        if paper is None:
            raise AppError("论文不存在", code="paper_not_found", status_code=404)
        if paper.was_checked_for_metadata and paper.has_metadata:
            return MetadataStatus.RECOGNIZED

        with self._storage.materialize(paper_pdf_key(paper.file_hash)) as path:
            identifiers = self._identifiers_from(path)
        if not identifiers:
            return self._record(paper_id, None, MetadataStatus.UNRECOGNIZED, None)

        identifier = preferred_identifier(identifiers)
        outcome = self._resolver.resolve(identifier)
        if outcome.metadata is None:
            return self._record(
                paper_id,
                None,
                outcome.status,
                [source_entry(identifier, outcome.source)],
            )

        metadata = outcome.metadata
        doi = metadata.doi or (
            identifier.value if identifier.type is IdentifierType.DOI else None
        )
        # Keep the version: an arXiv id with one names exactly one file.
        arxiv_id = metadata.arxiv_id or (
            identifier.full_value if identifier.type is IdentifierType.ARXIV else None
        )
        return self._record(
            paper_id,
            metadata.bibliographic(),
            outcome.status,
            [source_entry(identifier, outcome.source)],
            doi=doi,
            arxiv_id=arxiv_id,
        )

    def _identifiers_from(self, path: Path) -> list[Identifier]:
        try:
            return list(detect_identifiers(path))
        except Exception:  # a damaged file is a metadata problem, not a crash
            logger.warning("metadata.identification_failed")
            return []

    def _record(
        self,
        paper_id: UUID,
        bibliographic: dict | None,
        status: MetadataStatus,
        sources: list | None,
        *,
        doi: str | None = None,
        arxiv_id: str | None = None,
    ) -> MetadataStatus:
        paper = self._papers.get_paper(paper_id)
        # Fill-only: recognition never erases what is already known.
        merged = dict((paper.bibliographic if paper else None) or {})
        for key, value in (bibliographic or {}).items():
            if value and not merged.get(key):
                merged[key] = value
        self._papers.set_paper_metadata(
            paper_id,
            bibliographic=merged or None,
            metadata_sources=sources,
            doi=doi,
            arxiv_id=arxiv_id,
        )
        logger.info(
            "metadata.enriched",
            paper_id=str(paper_id),
            status=status.value,
        )
        return status
