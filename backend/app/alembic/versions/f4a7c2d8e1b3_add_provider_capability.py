"""add provider capability dimension

P5 供应商能力维度：
- provider_configs 新增 capability 列（chat/stt/tts/embedding/rerank），
  **默认 'chat'** 以兼容存量数据（迁移前的全部源都是对话源）。
- 「设为默认」的互斥范围从 user_id 升级为 (user_id, capability)：每种能力
  各自一条默认源。旧的 uq_provider_configs_default_per_user 索引因此被替换。
- 建新索引前先按 (user_id, capability) 组内去重——存量数据里同一用户理论上
  可能有两条 is_default=true（应用层互斥只是尽力而为），旧索引建时已去过一次，
  但保险起见按新维度再去一次。参照 e7f8a9b0c1d2 的做法。

Revision ID: f4a7c2d8e1b3
Revises: e2f6b3c7a9d4
Create Date: 2026-09-21 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a7c2d8e1b3"
down_revision: str | None = "e2f6b3c7a9d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) 新增能力列：NOT NULL + server_default 'chat'，存量行自动填为对话源
    op.add_column(
        "provider_configs",
        sa.Column(
            "capability",
            sa.String(length=20),
            nullable=False,
            server_default="chat",
        ),
    )

    # 2) 按新维度去重：每个 (user_id, capability) 只保留 updated_at 最新的一条默认源
    op.execute(
        """
        UPDATE provider_configs
        SET is_default = false
        WHERE is_default = true
          AND id NOT IN (
              SELECT DISTINCT ON (user_id, capability) id
              FROM provider_configs
              WHERE is_default = true
              ORDER BY user_id, capability, updated_at DESC
          )
        """
    )

    # 3) 索引换维度：旧的一用户一默认 → 一用户一能力一默认
    op.drop_index(
        "uq_provider_configs_default_per_user", table_name="provider_configs"
    )
    op.create_index(
        "uq_provider_configs_default_per_user_capability",
        "provider_configs",
        ["user_id", "capability"],
        unique=True,
        postgresql_where="is_default",
    )


def downgrade() -> None:
    # 回落：先按 user_id 去重（多种能力的默认源降级后只能留一条），再换回旧索引
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
    op.drop_index(
        "uq_provider_configs_default_per_user_capability",
        table_name="provider_configs",
    )
    op.create_index(
        "uq_provider_configs_default_per_user",
        "provider_configs",
        ["user_id"],
        unique=True,
        postgresql_where="is_default",
    )
    op.drop_column("provider_configs", "capability")
