"""Regression cases for PR #9's state and publication boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.library.repo import PaperRepository
from app.pipelines.domain import RunStage, RunStatus
from app.pipelines.repo import RunRepository
from app.pipelines.runs import RunService


@pytest.fixture(autouse=True)
def clean_database(clean_tables):
    return None


def test_claim_returns_nothing_when_the_only_run_is_already_leased(session_factory):
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="d" * 64, byte_size=100, page_count=1
        )
        RunRepository(session).add(paper.id)
        session.commit()
    with session_factory() as session:
        assert (
            RunRepository(session).claim_next(stage=RunStage.PARSE, lease_seconds=300)
            is not None
        )
    with session_factory() as session:
        assert (
            RunRepository(session).claim_next(stage=RunStage.PARSE, lease_seconds=300)
            is None
        )


def test_claim_uses_distinct_slots_when_two_papers_are_pending(session_factory):
    with session_factory() as session:
        for digest in ("2" * 64, "3" * 64):
            paper = PaperRepository(session).get_or_add_paper(
                file_hash=digest, byte_size=100, page_count=1
            )
            RunRepository(session).add(paper.id)
        session.commit()
    with session_factory() as session:
        first = RunRepository(session).claim_next(
            stage=RunStage.PARSE, lease_seconds=300
        )
    with session_factory() as session:
        second = RunRepository(session).claim_next(
            stage=RunStage.PARSE, lease_seconds=300
        )
    assert first is not None and second is not None
    assert first[0] != second[0]


def test_upload_title_stays_empty_when_a_private_filename_is_supplied(
    client, api_prefix, register_user, make_pdf, session_factory
):
    from tests.conftest import auth_headers

    user = register_user()
    response = client.post(
        f"{api_prefix}/papers",
        headers=auth_headers(user["access_token"]),
        files={"file": ("Alice-confidential.pdf", make_pdf(), "application/pdf")},
    )
    assert response.status_code == 202
    with session_factory() as session:
        run = RunRepository(session).get(UUID(response.json()["run_id"]))
        assert PaperRepository(session).get_paper(run.paper_id).title is None


def test_queue_keeps_original_failure_when_a_later_run_is_pending(
    session_factory, make_user
):
    from app.imports.service import ImportService

    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="e" * 64, byte_size=100, page_count=1
        )
        session.commit()
    first = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)
    with session_factory() as session:
        runs = RunRepository(session)
        runs.finish_failure(first.id, error_message="original failure")
        session.commit()
        runs.add(paper.id)
        session.commit()
    item = ImportService(session_factory=session_factory).queue(user_id=user_id)[0]
    assert item["run"]["status"] == "failed"
    assert item["run"]["error_message"] == "original failure"


def test_queue_exposes_owned_entry_when_the_user_has_a_completed_paper(
    session_factory, make_user
):
    from app.imports.service import ImportService

    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="f" * 64, byte_size=100, page_count=1
        )
        session.commit()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)
    with session_factory() as session:
        RunRepository(session).finish_success(run.id)
        entry = PaperRepository(session).link_paper(user_id=user_id, paper_id=paper.id)
        session.commit()
    item = ImportService(session_factory=session_factory).queue(user_id=user_id)[0]
    assert item["user_paper_id"] == str(entry.id)


def test_downloads_remain_independent_when_they_share_one_processing_run(
    session_factory, make_user
):
    from app.imports.service import ImportService
    from app.pipelines.repo import DownloadRepository

    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="1" * 64, byte_size=100, page_count=1
        )
        session.commit()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)
    with session_factory() as session:
        downloads = DownloadRepository(session)
        for _ in range(2):
            record = downloads.add(
                user_id=user_id, identifier_type="doi", identifier="10.1234/same"
            )
            downloads.finish_success(
                record.id, paper_id=paper.id, run_id=run.id, source_url=None
            )
        session.commit()
    items = ImportService(session_factory=session_factory).queue(user_id=user_id)
    assert len(items) == 2
    assert {item["source"] for item in items} == {"download"}


@pytest.mark.parametrize(
    "revision",
    [
        "20261024_0036_imports_own_progress.py",
        "20261026_0037_downloads_and_runs.py",
    ],
)
def test_paper_migration_preserves_bindings_when_clearing_paper_data(revision):
    import ast
    from pathlib import Path

    tree = ast.parse((Path("alembic/versions") / revision).read_text())
    cleared = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "CLEARED_TABLES" for t in node.targets
        )
    )
    assert "session_bindings" not in cleared
    assert "schedule_bindings" not in cleared


def test_project_paper_search_filters_by_the_shared_bibliographic_title(
    client, api_prefix, register_user, make_pdf, completed_imports, session_factory
):
    from app.library.repo import PaperRecord
    from tests.conftest import auth_headers

    account = register_user()
    headers = auth_headers(account["access_token"])
    project = client.post(
        f"{api_prefix}/projects", headers=headers, json={"name": "Reading"}
    ).json()["id"]
    client.post(
        f"{api_prefix}/papers",
        headers=headers,
        files={"file": ("private.pdf", make_pdf(), "application/pdf")},
        data={"project_id": project},
    )
    with session_factory() as session:
        paper = session.query(PaperRecord).one()
        paper.bibliographic = {"title": "Attention Is All You Need"}
        session.commit()
    found = client.get(
        f"{api_prefix}/projects/{project}/papers",
        headers=headers,
        params={"q": "attention"},
    )
    assert found.status_code == 200, found.text
    assert found.json()["total"] == 1
    missing = client.get(
        f"{api_prefix}/projects/{project}/papers",
        headers=headers,
        params={"q": "unrelated"},
    )
    assert missing.json()["total"] == 0


def test_a_reclaimed_run_refuses_any_late_publish_from_its_old_executor(
    session_factory, make_user
):
    from app.pipelines.repo import RunRecord

    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="4" * 64, byte_size=100, page_count=1
        )
        session.commit()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)
    with session_factory() as session:
        assert (
            RunRepository(session).claim_next(stage=RunStage.PARSE, lease_seconds=300)
        )[0] == run.id
    # The executor's guard connection died and its lease ran out.
    with session_factory() as session:
        record = session.get(RunRecord, run.id)
        record.leased_until = record.created_at
        session.commit()
    # With no executor holding the advisory lock, the run is reclaimed.
    with session_factory() as session:
        assert RunRepository(session).reclaim_expired() == 1
    with session_factory() as session:
        runs = RunRepository(session)
        # A late executor can neither start nor publish a stage, nor revive it.
        assert not runs.hold_ownership(run.id, lease_seconds=300)
        assert not runs.mark_stage_started(run.id, stage="parse")
        assert not runs.publish_stage(run.id, stage="parse")
        assert runs.get(run.id).status.value == "failed"


def test_finishing_hands_the_run_back_when_another_executor_holds_it(
    session_factory, make_user
):
    """A claim that cannot execute must not leave a running row behind."""
    from app.pipelines.repo import RunRecord

    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="5" * 64, byte_size=100, page_count=1
        )
        session.commit()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)
    with session_factory() as session:
        assert (
            RunRepository(session).claim_next(
                stage=RunStage.PARSE, lease_seconds=300
            )[0] == run.id
        )
    # The executor gives its own claim back when it never got the lock.
    with session_factory() as session:
        claimed_at = session.get(RunRecord, run.id).claim_token
    with session_factory() as session:
        assert RunRepository(session).release_claim(run.id, token=claimed_at)
        record = session.get(RunRecord, run.id)
        assert record.status == "pending"
        assert record.leased_until is None


def test_releasing_a_claim_is_refused_when_the_stage_moved_on(
    session_factory, make_user
):
    """Returning a claim must not undo work another executor already did."""
    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="6" * 64, byte_size=100, page_count=1
        )
        session.commit()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)
    with session_factory() as session:
        runs = RunRepository(session)
        runs.claim_next(stage=RunStage.PARSE, lease_seconds=300)
        runs.mark_stage_started(run.id, stage=RunStage.PARSE)
        runs.publish_stage(run.id, stage=RunStage.PARSE)
        runs.advance_stage(run.id, completed=RunStage.PARSE)
        session.commit()

    with session_factory() as session:
        # A stale stamp cannot undo work that moved on.
        assert not RunRepository(session).release_claim(run.id, token=uuid4())
        assert RunRepository(session).get(run.id).current_stage is RunStage.CHUNK


def test_a_stage_is_not_claimed_while_its_backoff_runs(
    session_factory, make_user
):
    """A deferred stage must wait: claiming it early burns the retry budget."""
    from app.pipelines.repo import RunRecord

    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="7" * 64, byte_size=100, page_count=1
        )
        session.commit()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)
    with session_factory() as session:
        runs = RunRepository(session)
        runs.claim_next(stage=RunStage.PARSE, lease_seconds=300)
        runs.mark_stage_started(run.id, stage=RunStage.PARSE)
        runs.defer_stage(
            run.id,
            stage=RunStage.PARSE,
            error_message="boom",
            max_attempts=3,
            base_seconds=60,
            max_seconds=300,
        )
        session.commit()

    with session_factory() as session:
        assert (
            RunRepository(session).claim_next(
                stage=RunStage.PARSE, lease_seconds=300
            )
            is None
        )

    # Once the backoff has passed the run becomes claimable again.
    with session_factory() as session:
        record = session.get(RunRecord, run.id)
        record.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    with session_factory() as session:
        assert (
            RunRepository(session).claim_next(
                stage=RunStage.PARSE, lease_seconds=300
            )[0] == run.id
        )


def test_each_stage_keeps_its_own_failure_count(session_factory, make_user):
    """One stage's failures must not consume another stage's budget."""
    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="8" * 64, byte_size=100, page_count=1
        )
        session.commit()
    run = RunService(session_factory).request(user_id=user_id, paper_id=paper.id)

    with session_factory() as session:
        runs = RunRepository(session)
        runs.claim_next(stage=RunStage.PARSE, lease_seconds=300)
        runs.mark_stage_started(run.id, stage=RunStage.PARSE)
        runs.defer_stage(
            run.id,
            stage=RunStage.PARSE,
            error_message="boom",
            max_attempts=3,
            base_seconds=60,
            max_seconds=300,
        )
        session.commit()

    with session_factory() as session:
        stored = RunRepository(session).get(run.id)
        assert stored.attempts_for(RunStage.PARSE) == 1
        assert stored.attempts_for(RunStage.CHUNK) == 0
        assert stored.status is RunStatus.PENDING


def test_a_heartbeat_cannot_invalidate_another_executors_claim(
    session_factory, make_user
):
    """The claim token must not move when the lease is renewed.

    A replaced claim's heartbeat keeps renewing the old lease; using the
    deadline as the claim identity would then make the live holder unable to
    give its claim back.
    """
    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="b9" * 32, byte_size=100, page_count=1
        )
        session.commit()
    RunService(session_factory).request(user_id=user_id, paper_id=paper.id)

    with session_factory() as session:
        runs = RunRepository(session)
        claimed = runs.claim_next(stage=RunStage.PARSE, lease_seconds=60)
    assert claimed is not None
    run_id, token = claimed

    # The heartbeat renews the lease: only the deadline moves.
    with session_factory() as session:
        assert RunRepository(session).renew_lease(
            run_id, lease_seconds=300, token=token
        )

    with session_factory() as session:
        stored = RunRepository(session).get(run_id)
        assert stored.claim_token == token

    # The holder can still give its claim back with the unchanged token.
    with session_factory() as session:
        assert RunRepository(session).release_claim(run_id, token=token)
        assert RunRepository(session).get(run_id).status is RunStatus.PENDING


def test_a_replaced_claim_cannot_renew_its_lease(session_factory, make_user):
    """An old heartbeat must not keep a run alive after its claim was replaced."""
    from app.pipelines.repo import RunRecord
    user_id = make_user()
    with session_factory() as session:
        paper = PaperRepository(session).get_or_add_paper(
            file_hash="a" * 64, byte_size=100, page_count=1
        )
        session.commit()
    RunService(session_factory).request(user_id=user_id, paper_id=paper.id)

    with session_factory() as session:
        claimed = RunRepository(session).claim_next(
            stage=RunStage.PARSE, lease_seconds=60
        )
    assert claimed is not None
    run_id, first_token = claimed

    # Someone else takes the run over with a fresh token.
    with session_factory() as session:
        record = session.get(RunRecord, run_id)
        record.claim_token = uuid4()
        session.commit()

    with session_factory() as session:
        assert not RunRepository(session).renew_lease(
            run_id, lease_seconds=300, token=first_token
        )
