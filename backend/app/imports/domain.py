"""Import domain: getting a source file in, then making it readable.

One import is one paper's whole journey into the library. The four stages differ
in what they compete for (network, MinerU pages, local CPU, embedding tokens),
so each gets its own queue and its own concurrency limit.

Bibliographic lookup is deliberately absent: it depends only on the stored file,
runs silently beside the stages, and never blocks an import from finishing.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ImportStage(StrEnum):
    """Artifact-producing steps of one import, in order."""

    SOURCE = "source"
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"


STAGE_ORDER: tuple[ImportStage, ...] = (
    ImportStage.SOURCE,
    ImportStage.PARSE,
    ImportStage.CHUNK,
    ImportStage.EMBED,
)

#: Stage label used by the interface, kept next to the enum so the two cannot
#: drift apart when a stage is renamed.
STAGE_TITLES: dict[ImportStage, str] = {
    ImportStage.SOURCE: "获取原文",
    ImportStage.PARSE: "解析正文",
    ImportStage.CHUNK: "切分片段",
    ImportStage.EMBED: "生成向量",
}


class ImportStatus(StrEnum):
    """Whole-import progress."""

    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    #: The identifier resolved but no public source file could be found.
    SOURCE_UNAVAILABLE = "source_unavailable"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL_STATUSES = {
    ImportStatus.READY,
    ImportStatus.FAILED,
    ImportStatus.SOURCE_UNAVAILABLE,
}
ACTIVE_STATUSES = {ImportStatus.QUEUED, ImportStatus.RUNNING}

#: Identifiers that a source file can come from.
IDENTIFIER_TYPES = {"doi", "arxiv", "upload"}


@dataclass(frozen=True, slots=True)
class ImportStageRecord:
    id: UUID
    stage: ImportStage
    status: StageStatus
    attempt: int
    error_code: str | None
    error_message: str | None
    progress: dict | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PaperImport:
    """How one paper entered the library.

    At most one per paper, so it describes the paper's own progress rather than
    a single request; two users importing the same file share the record.
    """

    id: UUID
    paper_id: UUID | None
    initiated_by: UUID
    identifier_type: str
    identifier: str
    status: ImportStatus
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stages: tuple[ImportStageRecord, ...]

    def stage(self, stage: ImportStage) -> ImportStageRecord | None:
        return next((item for item in self.stages if item.stage == stage), None)

    @property
    def current_stage(self) -> ImportStage | None:
        """The stage being worked on, for progress display."""
        for stage in STAGE_ORDER:
            record = self.stage(stage)
            if record is not None and record.status is StageStatus.RUNNING:
                return stage
        for stage in STAGE_ORDER:
            record = self.stage(stage)
            if record is not None and record.status is StageStatus.PENDING:
                return stage
        return None

    @property
    def finished_stages(self) -> set[ImportStage]:
        return {
            item.stage for item in self.stages if item.status is StageStatus.SUCCEEDED
        }


def source_of(identifier_type: str) -> "PaperSource":
    """Which door a paper came through, for the library entry."""
    from app.library.domain import PaperSource

    if identifier_type == "doi":
        return PaperSource.DOI
    if identifier_type == "arxiv":
        return PaperSource.ARXIV
    return PaperSource.UPLOAD
