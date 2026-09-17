"""remove items table (template leftover)

D1.4：删除 full-stack-fastapi-template 残留的示例待办表 item。
该表是模板 demo 用的示例数据（Item / ItemCreate / ItemUpdate / ItemPublic /
ItemsPublic 六个模型 + /api/v1/items 路由），IrsBot 的 Agent / RAG / 对话功能
均不使用它。

⚠️ 这是一次**破坏性**迁移：upgrade 会 DROP TABLE item，其中的示例数据不可恢复。
   downgrade 会重建表结构（仅结构，不含数据）。

Revision ID: f3e1a9b7c2d4
Revises: c1a2b3c4d5e6
Create Date: 2026-09-17 01:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3e1a9b7c2d4"
down_revision: str | None = "c1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("item")


def downgrade() -> None:
    op.create_table(
        "item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["user.id"], name=op.f("item_owner_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("item_pkey")),
    )
