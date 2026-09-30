from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app import config
from app.db import (
    Base,
    models,  # noqa: F401  # pyright: ignore[reportUnusedImport] (registers tables)
)

config_obj = context.config
if config_obj.config_file_name is not None:
    fileConfig(config_obj.config_file_name)

config_obj.set_main_option("sqlalchemy.url", config.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config_obj.get_section(config_obj.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
