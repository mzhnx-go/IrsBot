"""add age field to user

Revision ID: b2ae330a2811
Revises: fe56fa70289e
Create Date: 2026-06-09 22:01:34.075242

【迁移说明】
  - 目的：在 users 表中新增 age 列（用户年龄）
  - 变更：添加 age 字段，类型 VARCHAR(3)，允许为空
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'b2ae330a2811'       # 【当前版本号】这个迁移的唯一标识
down_revision = 'fe56fa70289e'   # 【上一个版本】基于哪个版本进行迁移
branch_labels = None
depends_on = None


def upgrade():
    # 【升级操作】执行迁移时运行的 SQL：给 user 表加一列 age
    # 等价于 SQL: ALTER TABLE user ADD COLUMN age VARCHAR(3) NULL;
    op.add_column('user', sa.Column('age', sqlmodel.sql.sqltypes.AutoString(length=3), nullable=True))


def downgrade():
    # 【回滚操作】撤销迁移时运行的 SQL：删除 age 列
    # 等价于 SQL: ALTER TABLE user DROP COLUMN age;
    op.drop_column('user', 'age')
