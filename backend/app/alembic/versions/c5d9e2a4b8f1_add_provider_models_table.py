"""add provider_models table

每个供应商可维护一份可用模型清单：
- 「获取模型列表」从上游 /models 拉取后 upsert
- 「自定义模型」手填 model_id
- (provider_id, model_id) 唯一，重复拉取幂等

Revision ID: c5d9e2a4b8f1
Revises: a1b2c3d4e5f7
Create Date: 2026-09-21 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d9e2a4b8f1"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 注意：index=True 会自动生成 ix_provider_models_provider_id，
    # 不能再显式 create_index 同名索引（DuplicateTable）。
    op.create_table(
        "provider_models",
        sa.Column("id", sa.UUID(), primary_key=False),
        sa.Column(
            "provider_id",
            sa.UUID(),
            sa.ForeignKey("provider_configs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "model_id",
            name="uq_provider_models_provider_model",
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_models")
