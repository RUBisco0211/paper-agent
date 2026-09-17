"""resize chunk embeddings for bge

Revision ID: 20260917_0007
Revises: 20260917_0006
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "20260917_0007"
down_revision: str | None = "20260917_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# BAAI/bge-m3 输出 1024 维。换模型/维度必须走一次离线迁移：
# 1) 改这里的维度；2) 重建 embedding 列；3) 重置 has_embedding，
#    让之后的重试任务重新生成向量（旧向量与新模型不可混用）。
NEW_DIMENSIONS = 1024
OLD_DIMENSIONS = 1536


def upgrade() -> None:
    # 维度变化无法就地转换，直接丢弃派生数据并重建列
    op.drop_column("chunks", "embedding")
    op.add_column(
        "chunks", sa.Column("embedding", Vector(NEW_DIMENSIONS), nullable=True)
    )
    op.execute("UPDATE papers SET has_embedding = false")


def downgrade() -> None:
    op.drop_column("chunks", "embedding")
    op.add_column(
        "chunks", sa.Column("embedding", Vector(OLD_DIMENSIONS), nullable=True)
    )
    op.execute("UPDATE papers SET has_embedding = false")
