"""Bind AgentScope sessions to business-owned scopes.

Revision ID: 20261005_0008
Revises: 20260917_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0008"
down_revision: str | None = "20260917_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_bindings",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
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
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_session_bindings_user_id", "session_bindings", ["user_id"])
    op.create_index(
        "ix_session_bindings_project_id", "session_bindings", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_bindings_project_id", table_name="session_bindings")
    op.drop_index("ix_session_bindings_user_id", table_name="session_bindings")
    op.drop_table("session_bindings")
