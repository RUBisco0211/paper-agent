"""Consolidate per-user preferences into one JSONB settings row.

Revision ID: 20261010_0018
Revises: 20261010_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20261010_0018"
down_revision: str | None = "20261010_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("config", JSONB(), nullable=False),
    )
    op.execute(
        "INSERT INTO user_settings (user_id, config) "
        "SELECT user_id, jsonb_build_object('version', 1, 'agent_tools', "
        "jsonb_build_object('always_allow', "
        "jsonb_object_agg(tool_name, always_allow))) "
        "FROM user_tool_authorizations GROUP BY user_id"
    )
    op.drop_index(
        "ix_user_tool_authorizations_user_id", table_name="user_tool_authorizations"
    )
    op.drop_table("user_tool_authorizations")


def downgrade() -> None:
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
    op.execute(
        "INSERT INTO user_tool_authorizations "
        "(id, user_id, tool_name, always_allow) "
        "SELECT gen_random_uuid(), user_id, policy.key, policy.value::boolean "
        "FROM user_settings, "
        "LATERAL jsonb_each_text(COALESCE(config #> "
        "'{agent_tools,always_allow}', '{}'::jsonb)) AS policy"
    )
    op.drop_table("user_settings")
