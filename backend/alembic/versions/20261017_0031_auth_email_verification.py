"""Record successful email verification for new accounts.

Revision ID: 20261017_0031
Revises: 20261010_0018
"""

import sqlalchemy as sa

from alembic import op

revision = "20261017_0031"
down_revision = "20261010_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
