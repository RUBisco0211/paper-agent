"""Persistent encrypted mail outbox.

Revision ID: 20261017_0033
Revises: 20261017_0032
"""

import sqlalchemy as sa

from alembic import op

revision = "20261017_0033"
down_revision = "20261017_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_outbox",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("dedupe_key", sa.String(240), nullable=False, unique=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(48)),
    )
    op.create_index("ix_mail_outbox_due", "mail_outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("mail_outbox")
