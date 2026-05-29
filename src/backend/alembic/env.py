import asyncio
from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

from sqlmodel import SQLModel

from app.database import make_engine

# Import all models so SQLModel registers their tables for autogenerate
from app.models import feedback, session  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    # Offline mode isn't wired up for this project (no-op placeholder).
    raise RuntimeError(
        "Offline migrations are not supported; run alembic without -x offline."
    )


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # NullPool because a migration run opens one short-lived connection and
    # should not share a pool with the app.
    connectable = make_engine(poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
