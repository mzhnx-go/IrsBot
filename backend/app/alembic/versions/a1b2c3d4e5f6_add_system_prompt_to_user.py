"""add system_prompt to user

为 User 表增加 system_prompt（TEXT，可空），用于存储用户自定义的
系统提示词（Agent 组装消息时注入最前面，防止暴露底层模型信息）。

Revision ID: a1b2c3d4e5f6
Revises: f3e1a9b7c2d4
Create Date: 2026-09-17 14:00:00
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f3e1a9b7c2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("system_prompt", sa.Text(), nullable=True),

    )

def downgrade() -> None:
    op.drop_column("user", "system_prompt")