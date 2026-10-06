"""Identify scheduled runs among project session bindings.

Revision ID: 20261006_0012
Revises: 20261006_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0012"
down_revision: str | None = "20261006_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_bindings", sa.Column("schedule_id", sa.String(64), nullable=True)
    )
    op.create_foreign_key(
        "fk_session_bindings_schedule_id",
        "session_bindings",
        "schedule_bindings",
        ["schedule_id"],
        ["schedule_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_session_bindings_schedule_id", "session_bindings", ["schedule_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_bindings_schedule_id", table_name="session_bindings")
    op.drop_constraint(
        "fk_session_bindings_schedule_id", "session_bindings", type_="foreignkey"
    )
    op.drop_column("session_bindings", "schedule_id")
