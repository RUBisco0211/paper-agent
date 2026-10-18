"""Fold the skipped ingestion stage status into succeeded.

A stage marked skipped already had verifiable output, so it carried the same
meaning as succeeded. Keeping it apart made the stage history depend on whether
a retry happened to re-run the stage.

Revision ID: 20261018_0034
Revises: 20261017_0033
"""

import sqlalchemy as sa

from alembic import op

revision = "20261018_0034"
down_revision = "20261017_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ingestion_stages SET status = 'succeeded' WHERE status = 'skipped'"
        )
    )


def downgrade() -> None:
    """Irreversible: folded rows cannot be told apart after the upgrade."""
