"""Add the per-user store for third-party service credentials.

Revision ID: 20261022_0035
Revises: 20261018_0034
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261022_0035"
down_revision = "20261018_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_credentials",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "kind", name="uq_service_credentials_user_kind"),
    )
    op.create_index(
        "ix_service_credentials_user",
        "service_credentials",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_service_credentials_user", table_name="service_credentials")
    op.drop_table("service_credentials")
