"""Register evidence for AgentScope session citations.

Revision ID: 20261005_0009
Revises: 20261005_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20261005_0009"
down_revision: str | None = "20261005_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_bound_citations",
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("session_bindings.session_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("citation_id", sa.String(64), primary_key=True),
        sa.Column(
            "user_paper_id",
            sa.Uuid(),
            sa.ForeignKey("user_papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_ids", JSONB(), nullable=False),
        sa.Column("title_path", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("session_bound_citations")
