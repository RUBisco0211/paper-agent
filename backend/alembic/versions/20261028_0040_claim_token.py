"""Identify a claim by a token that survives lease renewals.

The lease deadline moves every time the executor renews it, so it cannot say
who holds the claim. Releasing or renewing with a stale stamp then either
undoes a live claim or keeps a dead one alive.

Revision ID: 20261028_0040
Revises: 20261027_0039
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261028_0040"
down_revision: str | None = "20261027_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("claim_token", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "claim_token")
