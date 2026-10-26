"""Requests remember which project they also want, and the queue reads them.

A download is not the only way a paper arrives: an upload has no download row at
all. So the queue has to be the union of what the user asked for, which is
`user_runs`, plus the downloads that carry the fetching step. Both records gain
the project the request asked to file the paper into, and that project is
checked when the request is accepted.

Revision ID: 20261026_0038
Revises: 20261026_0037
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261026_0038"
down_revision: str | None = "20261026_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_runs", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "user_runs_project_id_fkey",
        "user_runs",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_user_runs_project_id", "user_runs", ["project_id"])

    op.add_column("downloads", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "downloads_project_id_fkey",
        "downloads",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("downloads_project_id_fkey", "downloads", type_="foreignkey")
    op.drop_column("downloads", "project_id")
    op.drop_index("ix_user_runs_project_id", table_name="user_runs")
    op.drop_constraint("user_runs_project_id_fkey", "user_runs", type_="foreignkey")
    op.drop_column("user_runs", "project_id")
