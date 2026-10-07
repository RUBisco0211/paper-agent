"""Record the published MinerU artifact generation.

Revision ID: 20261007_0014
Revises: 20261007_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261007_0014"
down_revision: str | None = "20261007_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "papers", sa.Column("artifact_manifest_key", sa.Text(), nullable=True)
    )
    op.create_index(
        "uq_ingestion_one_active_job_per_paper",
        "ingestion_jobs",
        ["paper_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_ingestion_one_active_job_per_paper", table_name="ingestion_jobs")
    op.drop_column("papers", "artifact_manifest_key")
