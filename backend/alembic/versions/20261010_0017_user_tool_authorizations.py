"""Store per-user approval policy for reviewed Agent tools.

Revision ID: 20261010_0017
Revises: 20261008_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0017"
down_revision: str | None = "20261008_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_tool_authorizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column(
            "always_allow", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.UniqueConstraint("user_id", "tool_name"),
    )
    op.create_index(
        "ix_user_tool_authorizations_user_id", "user_tool_authorizations", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_tool_authorizations_user_id", table_name="user_tool_authorizations"
    )
    op.drop_table("user_tool_authorizations")
