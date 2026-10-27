"""Runs are claimed one stage at a time, so a stage can retry on its own.

Each stage now counts its own failures and can wait before being tried again.
The queue index covers only the rows that are ready right now: a run waiting
out its backoff does not sit in the index at all.

Revision ID: 20261027_0039
Revises: 20261026_0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261027_0039"
down_revision: str | None = "20261026_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "stage_attempts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "runs",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Claiming no longer filters on status alone.
    op.drop_index("ix_runs_status", table_name="runs")
    op.create_index(
        "ix_runs_stage_queue",
        "runs",
        ["current_stage", "created_at"],
        unique=False,
        postgresql_where=sa.text(
            "status = 'pending' AND next_attempt_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_runs_stage_queue", table_name="runs")
    op.create_index("ix_runs_status", "runs", ["status"])
    op.drop_column("runs", "next_attempt_at")
    op.drop_column("runs", "stage_attempts")
