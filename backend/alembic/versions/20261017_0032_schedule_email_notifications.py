"""Add opt-in email notifications to schedule bindings.

Revision ID: 20261017_0032
Revises: 20261017_0031
"""

import sqlalchemy as sa

from alembic import op

revision = "20261017_0032"
down_revision = "20261017_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_bindings",
        sa.Column(
            "notify_email", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_bindings", "notify_email")
