"""Retire the business-service session tables after AgentScope takeover.

Revision ID: 20261006_0010
Revises: 20261005_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261006_0010"
down_revision: str | None = "20261005_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM sessions")).scalar_one()
    if count:
        raise RuntimeError(
            "legacy_sessions_not_empty: export old session history before migration"
        )
    op.drop_index(
        op.f("ix_session_pending_messages_session_id"),
        table_name="session_pending_messages",
    )
    op.drop_table("session_pending_messages")
    op.drop_index(
        op.f("ix_session_citations_user_paper_id"), table_name="session_citations"
    )
    op.drop_index(
        op.f("ix_session_citations_session_id"), table_name="session_citations"
    )
    op.drop_table("session_citations")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_project_id"), table_name="sessions")
    op.drop_table("sessions")


def downgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sessions_project_id"), "sessions", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "session_citations",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("citation_id", sa.String(length=64), nullable=False),
        sa.Column("user_paper_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("title_path", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_paper_id"], ["user_papers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "citation_id", name="uq_session_citation"),
    )
    op.create_index(
        op.f("ix_session_citations_session_id"),
        "session_citations",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_citations_user_paper_id"),
        "session_citations",
        ["user_paper_id"],
        unique=False,
    )
    op.create_table(
        "session_pending_messages",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("delivery", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "delivery", "position", name="uq_pending_order"
        ),
    )
    op.create_index(
        op.f("ix_session_pending_messages_session_id"),
        "session_pending_messages",
        ["session_id"],
        unique=False,
    )
