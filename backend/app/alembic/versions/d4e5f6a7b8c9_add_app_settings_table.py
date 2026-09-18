"""add app_settings table

新增 app_settings（通用 KV 表），用于存放**可在运行时变更**的系统配置。
首个键为 `users.open_registration`，控制匿名自助注册是否开放
（超管在 /admin 页切换，立即生效，无需重启）。

与 `.env` 的关系：`.env` 是部署级配置 + 本表的**兜底初值**，本表有记录时
覆盖 `.env`。因此升级后（表为空）系统行为与升级前**完全一致**。

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-09-18 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
