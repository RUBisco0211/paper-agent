"""Store explicit, session-bound batch import approvals.

Revision ID: 20261008_0016
Revises: 20261007_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20261008_0016"
down_revision: str | None = "20261007_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("candidates", JSONB(), nullable=False),
        sa.Column("results", JSONB(), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_import_approvals_user_id", "import_approvals", ["user_id"])
    op.create_index("ix_import_approvals_session_id", "import_approvals", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_import_approvals_session_id", table_name="import_approvals")
    op.drop_index("ix_import_approvals_user_id", table_name="import_approvals")
    op.drop_table("import_approvals")
