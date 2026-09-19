"""uq_provider_configs_default_per_user

为 provider_configs 增加部分唯一索引：同一 user_id 下最多一条
is_default=true 的记录（只约束为真的行，false 行不受影响）。

应用层的互斥清零只是「尽力而为」，并发写仍可能落进两条默认源；
该索引在数据库层面兜底。建索引前先把存量脏数据去重：
每个 user_id 保留 updated_at 最新的一条默认源，其余置为 false。

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-09-20 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) 存量去重：每个用户保留最新的那条默认源，其余降级为非默认
    op.execute(
        """
        UPDATE provider_configs
        SET is_default = false
        WHERE is_default = true
          AND id NOT IN (
              SELECT DISTINCT ON (user_id) id
              FROM provider_configs
              WHERE is_default = true
              ORDER BY user_id, updated_at DESC
          )
        """
    )
    # 2) 建部分唯一索引（PostgreSQL）
    op.create_index(
        "uq_provider_configs_default_per_user",
        "provider_configs",
        ["user_id"],
        unique=True,
        postgresql_where="is_default",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_provider_configs_default_per_user", table_name="provider_configs"
    )
