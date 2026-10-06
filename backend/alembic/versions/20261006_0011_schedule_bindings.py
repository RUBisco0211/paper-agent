"""Bind AgentScope schedules to owned projects.

Revision ID: 20261006_0011
Revises: 20261006_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0011"
down_revision: str | None = "20261006_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_bindings",
        sa.Column("schedule_id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_schedule_bindings_user_id", "schedule_bindings", ["user_id"])
    op.create_index(
        "ix_schedule_bindings_project_id", "schedule_bindings", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_bindings_project_id", table_name="schedule_bindings")
    op.drop_index("ix_schedule_bindings_user_id", table_name="schedule_bindings")
    op.drop_table("schedule_bindings")
