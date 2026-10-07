"""Allow scheduled runs to use the user's full library scope.

Revision ID: 20261007_0013
Revises: 20261006_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261007_0013"
down_revision: str | None = "20261006_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "schedule_bindings", "project_id", existing_type=sa.Uuid(), nullable=True
    )


def downgrade() -> None:
    if op.get_bind().execute(
        sa.text("SELECT 1 FROM schedule_bindings WHERE project_id IS NULL LIMIT 1")
    ).first():
        raise RuntimeError("Remove global schedules before downgrading")
    op.alter_column(
        "schedule_bindings", "project_id", existing_type=sa.Uuid(), nullable=False
    )
