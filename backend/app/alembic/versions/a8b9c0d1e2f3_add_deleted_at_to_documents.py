"""add_deleted_at_to_documents

给 documents 增加软删除标记 deleted_at（UTC，NULL = 正常文档）。

背景：删除文档原先直接清三处（Milvus 向量 / 磁盘文件 / DB 记录），
误删无法挽回。改为软删除后，Milvus 向量仍然立即清（保证检索不到），
但磁盘文件保留 N 天、DB 记录打上 deleted_at，期间可恢复到原知识库。

Revision ID: a8b9c0d1e2f3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-20 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 活跃文档列表 / 回收站列表 / 过期清理都以该列为过滤条件
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_column("documents", "deleted_at")