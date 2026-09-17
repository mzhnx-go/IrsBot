import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, Table, Column, engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
assert config.config_file_name is not None
fileConfig(config.config_file_name)

from app.core.db.sqlmodel_models import SQLModel  # noqa
from app.core.config import settings  # noqa

# 所有模型（User 与 9 张业务表）统一注册在 SQLModel.metadata 下
# （Item 示例表已随 D1.4 删除）
target_metadata = SQLModel.metadata


def _include_object(object, name, type_, reflected, compare_to):
    """Include all objects from the combined metadata."""
    return True


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = str(settings.SQLALCHEMY_DATABASE_URI)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    assert configuration is not None
    configuration["sqlalchemy.url"] = str(settings.SQLALCHEMY_DATABASE_URI)
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
