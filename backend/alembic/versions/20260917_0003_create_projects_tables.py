"""create projects tables

Revision ID: 20260917_0003
Revises: 20260917_0002
Create Date: 2026-09-17 00:20:14.496451
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0003"
down_revision: str | None = "20260917_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)
    op.create_table(
        "project_papers",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_paper_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_paper_id"], ["user_papers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_paper_id", name="uq_project_paper"),
    )
    op.create_index(
        op.f("ix_project_papers_project_id"),
        "project_papers",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_papers_user_paper_id"),
        "project_papers",
        ["user_paper_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_papers_user_paper_id"), table_name="project_papers")
    op.drop_index(op.f("ix_project_papers_project_id"), table_name="project_papers")
    op.drop_table("project_papers")
    op.drop_index(op.f("ix_projects_user_id"), table_name="projects")
    op.drop_table("projects")
