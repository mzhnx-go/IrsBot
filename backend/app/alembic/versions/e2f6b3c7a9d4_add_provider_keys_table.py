"""add provider_keys table

同一供应商支持多把 API Key（P8「添加更多」）：
- 迁移时把 provider_configs.api_key 回填为首行（resolve_key 的权威来源），
  原列保留作为无行时的回落。
- provider_id 级联删除。

Revision ID: e2f6b3c7a9d4
Revises: c5d9e2a4b8f1
Create Date: 2026-09-21 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f6b3c7a9d4"
down_revision: str | None = "c5d9e2a4b8f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_keys",
        sa.Column("id", sa.UUID(), primary_key=False),
        sa.Column(
            "provider_id",
            sa.UUID(),
            sa.ForeignKey("provider_configs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # 回填：每个供应商现有的密文 Key 成为第一行
    op.execute(
        "INSERT INTO provider_keys "
        "(id, provider_id, encrypted_key, is_active, fail_count, created_at) "
        "SELECT gen_random_uuid(), id, api_key, true, 0, now() "
        "FROM provider_configs"
    )


def downgrade() -> None:
    op.drop_table("provider_keys")
