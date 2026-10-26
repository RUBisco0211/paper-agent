"""Regression cases for PR #9's state and publication boundaries."""

from uuid import UUID

import pytest

from app.library.repo import PaperRepository
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
        assert RunRepository(session).claim_next(lease_seconds=300) is not None
    with session_factory() as session:
        assert RunRepository(session).claim_next(lease_seconds=300) is None


def test_claim_uses_distinct_slots_when_two_papers_are_pending(session_factory):
    with session_factory() as session:
        for digest in ("2" * 64, "3" * 64):
            paper = PaperRepository(session).get_or_add_paper(
                file_hash=digest, byte_size=100, page_count=1
            )
            RunRepository(session).add(paper.id)
        session.commit()
    with session_factory() as session:
        first = RunRepository(session).claim_next(lease_seconds=300)
    with session_factory() as session:
        second = RunRepository(session).claim_next(lease_seconds=300)
    assert first is not None and second is not None and first != second


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
