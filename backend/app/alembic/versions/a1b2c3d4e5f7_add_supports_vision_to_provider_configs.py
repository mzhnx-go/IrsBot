"""add_supports_vision_to_provider_configs

为 provider_configs 增加 supports_vision 三态标记：
- NULL（默认）= 自动，按模型名启发式判断
- true  = 显式声明支持视觉
- false = 显式声明不支持

存量记录一律留 NULL（自动），行为与升级前一致。

Revision ID: a1b2c3d4e5f7
Revises: b7c9d1e3f5a7
Create Date: 2026-09-21 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "b7c9d1e3f5a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_configs",
        sa.Column("supports_vision", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_configs", "supports_vision")
