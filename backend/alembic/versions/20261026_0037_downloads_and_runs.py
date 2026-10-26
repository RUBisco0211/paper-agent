"""Downloads and runs replace the single import record.

An import used to be one row per paper carrying both "who asked" and "how far
the file got". That made one user's failure other users' failure. Now a request
to fetch an identifier (``downloads``, one row per attempt, per user) is separate
from a paper's processing (``runs``, at most one active per paper), and
``user_runs`` says who is waiting on it.

Progress is no longer a stage table: a run keeps its current stage, an error
message and per-stage timings inline. Entries only exist once a run succeeded,
so ``user_papers`` loses both ``ready`` and the import-source label.

Existing paper data is cleared rather than migrated: the old rows carry progress
in places that no longer exist.

Revision ID: 20261026_0037
Revises: 20261024_0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261026_0037"
down_revision: str | None = "20261024_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Cleared children first; ``projects`` survives, only its paper links go.
CLEARED_TABLES = (
    "session_bound_citations",
    "session_bindings",
    "schedule_bindings",
    "project_papers",
    "import_approvals",
    "import_stages",
    "paper_imports",
    "chunks",
    "user_papers",
    "papers",
)


def upgrade() -> None:
    for table in CLEARED_TABLES:
        op.execute(f"DELETE FROM {table}")

    op.create_table(
        "runs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_stage", sa.String(length=16), nullable=True),
        sa.Column(
            "stage_timings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_paper_id", "runs", ["paper_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    # One active run per paper is a rule of the model, not a convention.
    op.create_index(
        "uq_runs_one_active_per_paper",
        "runs",
        ["paper_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    op.create_table(
        "downloads",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("identifier_type", sa.String(length=16), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_downloads_user_id", "downloads", ["user_id"])
    op.create_index("ix_downloads_status", "downloads", ["status"])

    op.create_table(
        "user_runs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_runs_user_id", "user_runs", ["user_id"])
    op.create_index("ix_user_runs_run_id", "user_runs", ["run_id"])
    op.create_index("ix_user_runs_paper_id", "user_runs", ["paper_id"])

    op.drop_table("import_stages")
    op.drop_table("paper_imports")

    # An entry means "usable": there is no half-built entry to hide any more.
    op.drop_column("user_papers", "ready")
    op.drop_column("user_papers", "source")


def downgrade() -> None:
    op.add_column(
        "user_papers",
        sa.Column(
            "source", sa.String(length=16), server_default="upload", nullable=False
        ),
    )
    op.add_column(
        "user_papers",
        sa.Column(
            "ready", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.execute("UPDATE user_papers SET ready = true")

    op.create_table(
        "paper_imports",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("paper_id", sa.Uuid(), nullable=True),
        sa.Column("initiated_by", sa.Uuid(), nullable=False),
        sa.Column("identifier_type", sa.String(length=16), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_imports_initiated_by", "paper_imports", ["initiated_by"])
    op.create_index(
        "uq_paper_imports_one_per_paper",
        "paper_imports",
        ["paper_id"],
        unique=True,
        postgresql_where=sa.text("paper_id IS NOT NULL"),
    )

    op.create_table(
        "import_stages",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_id"], ["paper_imports.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_id", "stage", name="uq_import_stage"),
    )
    op.create_index("ix_import_stages_import_id", "import_stages", ["import_id"])

    op.drop_index("ix_user_runs_paper_id", table_name="user_runs")
    op.drop_index("ix_user_runs_run_id", table_name="user_runs")
    op.drop_index("ix_user_runs_user_id", table_name="user_runs")
    op.drop_table("user_runs")
    op.drop_index("ix_downloads_status", table_name="downloads")
    op.drop_index("ix_downloads_user_id", table_name="downloads")
    op.drop_table("downloads")
    op.drop_index("uq_runs_one_active_per_paper", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_paper_id", table_name="runs")
    op.drop_table("runs")
