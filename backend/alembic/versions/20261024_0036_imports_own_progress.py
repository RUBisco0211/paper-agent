"""One import record per paper; papers own the bibliographic facts.

An entry always points at a paper whose source file is stored, and the paper is
the single owner of title, authors and identifiers. Progress belongs to the
import that brought the paper in, so the paper carries no completion flags and
no metadata status enum.

`ingestion_jobs` disappears: a paper has at most one import, and its four
stages live in `import_stages`. Existing paper data is cleared rather than
migrated, because two independent writers produced the entry and paper copies
that this change removes.

Revision ID: 20261024_0036
Revises: 20261022_0035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0036"
down_revision: str | None = "20261022_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Cleared children first. ``projects`` survives; only its paper links go.
CLEARED_TABLES = (
    "session_bound_citations",
    "session_bindings",
    "schedule_bindings",
    "project_papers",
    "import_approvals",
    "ingestion_stages",
    "ingestion_jobs",
    "paper_imports",
    "chunks",
    "user_papers",
    "papers",
)

#: Columns removed from papers: every one of them was a copy of a fact that
#: lives on the artifact itself or on the import record.
DROPPED_PAPER_COLUMNS = (
    "metadata_status",
    "has_metadata",
    "has_fulltext",
    "has_keyword_index",
    "has_embedding",
)


def upgrade() -> None:
    for table in CLEARED_TABLES:
        op.execute(f"DELETE FROM {table}")

    op.add_column("papers", sa.Column("doi", sa.String(length=255), nullable=True))
    op.add_column("papers", sa.Column("arxiv_id", sa.String(length=64), nullable=True))
    op.create_index("ix_papers_doi", "papers", ["doi"], unique=False)
    op.create_index("ix_papers_arxiv_id", "papers", ["arxiv_id"], unique=False)
    for column in DROPPED_PAPER_COLUMNS:
        op.drop_column("papers", column)

    # An entry no longer carries bibliographic copies, and always points at a
    # paper that has a source file.
    op.alter_column("user_papers", "paper_id", nullable=False)
    # An entry exists as soon as its paper has a stored file, but the library
    # hides it until every stage finished.
    op.add_column(
        "user_papers",
        sa.Column(
            "ready", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    for column in (
        "title",
        "authors",
        "abstract",
        "doi",
        "arxiv_id",
        "year",
        "venue",
        "metadata",
        "metadata_status",
        "metadata_sources",
        "original_filename",
    ):
        op.drop_column("user_papers", column)

    # paper_imports becomes the paper's own progress, not a user request.
    op.alter_column("paper_imports", "user_id", new_column_name="initiated_by")
    op.drop_constraint(
        "paper_imports_user_id_fkey", "paper_imports", type_="foreignkey"
    )
    op.create_foreign_key(
        "paper_imports_initiated_by_fkey",
        "paper_imports",
        "users",
        ["initiated_by"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("DROP INDEX IF EXISTS ix_paper_imports_user_id")
    op.create_index("ix_paper_imports_initiated_by", "paper_imports", ["initiated_by"])
    op.drop_constraint(
        "paper_imports_project_id_fkey", "paper_imports", type_="foreignkey"
    )
    op.drop_constraint(
        "paper_imports_user_paper_id_fkey", "paper_imports", type_="foreignkey"
    )
    op.drop_column("paper_imports", "project_id")
    op.drop_column("paper_imports", "user_paper_id")
    op.drop_column("paper_imports", "metadata_source")
    op.add_column(
        "paper_imports", sa.Column("paper_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "paper_imports",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "paper_imports_paper_id_fkey",
        "paper_imports",
        "papers",
        ["paper_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_paper_imports_one_per_paper",
        "paper_imports",
        ["paper_id"],
        unique=True,
        postgresql_where=sa.text("paper_id IS NOT NULL"),
    )

    # Stage rows now belong to the import rather than to a job table.
    op.rename_table("ingestion_stages", "import_stages")
    op.execute(
        "DO $$ BEGIN "
        "ALTER INDEX ingestion_stages_pkey RENAME TO import_stages_pkey; "
        "EXCEPTION WHEN undefined_table THEN NULL; "
        "END $$"
    )
    op.drop_constraint(
        "ingestion_stages_ingestion_job_id_fkey", "import_stages", type_="foreignkey"
    )
    op.alter_column(
        "import_stages", "ingestion_job_id", new_column_name="import_id"
    )
    op.create_foreign_key(
        "import_stages_import_id_fkey",
        "import_stages",
        "paper_imports",
        ["import_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        "ALTER INDEX ix_ingestion_stages_ingestion_job_id "
        "RENAME TO ix_import_stages_import_id"
    )
    op.drop_constraint("uq_ingestion_stage", "import_stages", type_="unique")
    op.create_unique_constraint(
        "uq_import_stage", "import_stages", ["import_id", "stage"]
    )

    op.drop_table("ingestion_jobs")


def downgrade() -> None:
    # The previous model had many entries without a source file and one job row
    # per paper; both are reconstructed empty because the data was cleared.
    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_stage", sa.String(length=16), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ingestion_jobs_paper_id"), "ingestion_jobs", ["paper_id"]
    )

    op.drop_constraint("uq_import_stage", "import_stages", type_="unique")
    op.create_unique_constraint(
        "uq_ingestion_stage", "import_stages", ["import_id", "stage"]
    )
    op.execute(
        "ALTER INDEX ix_import_stages_import_id "
        "RENAME TO ix_ingestion_stages_ingestion_job_id"
    )
    op.drop_constraint(
        "import_stages_import_id_fkey", "import_stages", type_="foreignkey"
    )
    op.alter_column(
        "import_stages", "import_id", new_column_name="ingestion_job_id"
    )
    op.create_foreign_key(
        "ingestion_stages_ingestion_job_id_fkey",
        "import_stages",
        "ingestion_jobs",
        ["ingestion_job_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        "DO $$ BEGIN "
        "ALTER INDEX import_stages_pkey RENAME TO ingestion_stages_pkey; "
        "EXCEPTION WHEN undefined_table THEN NULL; "
        "END $$"
    )
    op.rename_table("import_stages", "ingestion_stages")

    op.drop_index("uq_paper_imports_one_per_paper", table_name="paper_imports")
    op.drop_constraint(
        "paper_imports_paper_id_fkey", "paper_imports", type_="foreignkey"
    )
    op.drop_column("paper_imports", "started_at")
    op.drop_column("paper_imports", "paper_id")
    op.add_column(
        "paper_imports", sa.Column("metadata_source", sa.String(32), nullable=True)
    )
    op.add_column(
        "paper_imports", sa.Column("user_paper_id", sa.Uuid(), nullable=True)
    )
    op.add_column("paper_imports", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "paper_imports_project_id_fkey",
        "paper_imports",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "paper_imports_user_paper_id_fkey",
        "paper_imports",
        "user_papers",
        ["user_paper_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "paper_imports_initiated_by_fkey", "paper_imports", type_="foreignkey"
    )
    op.alter_column("paper_imports", "initiated_by", new_column_name="user_id")
    op.create_foreign_key(
        "paper_imports_user_id_fkey",
        "paper_imports",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("DROP INDEX IF EXISTS ix_paper_imports_initiated_by")
    op.create_index("ix_paper_imports_user_id", "paper_imports", ["user_id"])

    op.add_column("user_papers", sa.Column("title", sa.String(512), nullable=True))
    op.add_column(
        "user_papers", sa.Column("authors", postgresql.JSONB(), nullable=True)
    )
    op.add_column("user_papers", sa.Column("abstract", sa.Text(), nullable=True))
    op.add_column("user_papers", sa.Column("doi", sa.String(255), nullable=True))
    op.add_column("user_papers", sa.Column("arxiv_id", sa.String(64), nullable=True))
    op.add_column("user_papers", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("user_papers", sa.Column("venue", sa.String(255), nullable=True))
    op.add_column(
        "user_papers", sa.Column("metadata", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "user_papers",
        sa.Column(
            "metadata_status",
            sa.String(32),
            nullable=False,
            server_default="unrecognized",
        ),
    )
    op.add_column(
        "user_papers", sa.Column("metadata_sources", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "user_papers", sa.Column("original_filename", sa.String(512), nullable=True)
    )
    op.drop_column("user_papers", "ready")
    op.create_index("ix_user_papers_user_doi", "user_papers", ["doi"])
    op.create_index("ix_user_papers_user_arxiv", "user_papers", ["arxiv_id"])
    op.alter_column("user_papers", "paper_id", nullable=False)

    op.add_column(
        "papers",
        sa.Column(
            "metadata_status",
            sa.String(32),
            nullable=False,
            server_default="unrecognized",
        ),
    )
    for column in ("has_metadata", "has_fulltext", "has_keyword_index", "has_embedding"):
        op.add_column(
            "papers",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.drop_index("ix_papers_arxiv_id", table_name="papers")
    op.drop_index("ix_papers_doi", table_name="papers")
    op.drop_column("papers", "arxiv_id")
    op.drop_column("papers", "doi")
