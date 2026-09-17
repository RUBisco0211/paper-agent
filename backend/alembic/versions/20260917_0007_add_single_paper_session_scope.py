"""add single paper session scope

Revision ID: 20260917_0007
Revises: 20260917_0006
Create Date: 2026-09-17 09:39:55.888463
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0007"
down_revision: str | None = "20260917_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("user_paper_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_sessions_user_paper_id"), "sessions", ["user_paper_id"], unique=False
    )
    op.create_foreign_key(
        "fk_sessions_user_paper_id",
        "sessions",
        "user_papers",
        ["user_paper_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_sessions_user_paper_id", "sessions", type_="foreignkey")
    op.drop_index(op.f("ix_sessions_user_paper_id"), table_name="sessions")
    op.drop_column("sessions", "user_paper_id")
