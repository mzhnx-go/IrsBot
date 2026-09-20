"""add is_enabled to conversations

为 Conversation 表增加 is_enabled（BOOLEAN，默认 TRUE），用于会话级
启用/停用开关。Pipeline 的 SessionStatus 阶段据此拦截被停用会话的消息
（Phase 12.1 决策表结论）。

Revision ID: b7c9d1e3f5a7
Revises: a8b9c0d1e2f3
Create Date: 2026-09-20 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c9d1e3f5a7"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "is_enabled")
