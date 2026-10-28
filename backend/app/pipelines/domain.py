"""Getting a file and processing it: two records, two lifecycles.

A download belongs to one user's request for one identifier and may find
nothing. A run belongs to one paper and always ends with a result. Keeping them
apart lets the paper only exist once a file does, so every run binds a paper
that is already stored.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class RunStage(StrEnum):
    """Artifact-producing steps of one run, in order."""

    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"


STAGE_ORDER: tuple[RunStage, ...] = (
    RunStage.PARSE,
    RunStage.CHUNK,
    RunStage.EMBED,
)

#: Interface labels, kept beside the enum so renaming a stage cannot drift.
STAGE_TITLES: dict[RunStage, str] = {
    RunStage.PARSE: "解析正文",
    RunStage.CHUNK: "切分片段",
    RunStage.EMBED: "生成向量",
}


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


ACTIVE_RUN_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING}


class DownloadStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


ACTIVE_DOWNLOAD_STATUSES = {DownloadStatus.PENDING, DownloadStatus.RUNNING}


def next_stage(stage: RunStage) -> RunStage | None:
    """The stage after this one, or nothing when this was the last."""
    index = STAGE_ORDER.index(stage)
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None


@dataclass(frozen=True, slots=True)
class StageTiming:
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Download:
    """One user's request to turn an identifier into a stored file."""

    id: UUID
    user_id: UUID
    identifier_type: str
    identifier: str
    status: DownloadStatus
    paper_id: UUID | None
    run_id: UUID | None
    #: Project the requester also wants this paper filed into.
    project_id: UUID | None
    source_url: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @property
    def is_finished(self) -> bool:
        return self.status in {DownloadStatus.SUCCESS, DownloadStatus.FAILED}


@dataclass(frozen=True, slots=True)
class Run:
    """One processing attempt for a paper; at most one is active per paper."""

    id: UUID
    paper_id: UUID
    status: RunStatus
    current_stage: RunStage | None
    stage_timings: dict[str, StageTiming]
    #: Failures per stage, e.g. {"parse": 2}.
    stage_attempts: dict[str, int]
    #: When the current stage may be tried again; null means "right now".
    next_attempt_at: datetime | None
    #: Opaque stamp identifying the current claim; survives lease renewals.
    claim_token: UUID | None
    error_message: str | None
    leased_until: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    def attempts_for(self, stage: RunStage) -> int:
        return int(self.stage_attempts.get(stage.value, 0))

    def timing(self, stage: RunStage) -> StageTiming:
        return self.stage_timings.get(stage.value, StageTiming())

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_RUN_STATUSES
