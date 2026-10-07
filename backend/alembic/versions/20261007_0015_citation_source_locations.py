"""Persist registered citation source coordinates across reindexing.

Revision ID: 20261007_0015
Revises: 20261007_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20261007_0015"
down_revision: str | None = "20261007_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_bound_citations",
        sa.Column("source_locations", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_bound_citations", "source_locations")
