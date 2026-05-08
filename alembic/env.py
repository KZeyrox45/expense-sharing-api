# Configure Alembic to run migrations with async SQLAlchemy.

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Read config from alembic.ini
alembic_config = context.config
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# --- Import Settings and Models ------------------------------------
# IMPORTANT: Must import Base and all models before using
# target_metadata for autogenerate to know which tables are available
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import *     # noqa: E402, F401, F403 - Import all models


# Override DATABASE_URL from .env instead of hardcoding in alembic.ini
alembic_config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


# --- Offline mode --------------------------------------------------
# Run when no actual database connection is required (only generates SQL scripts).
def run_migrations_offline() -> None:
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# --- Online mode ----------------------------------------------------
# Runs when a real database connection is established,
# requires the use of asyncio because the engine is async.
def do_run_migrations(connection: Connection) -> None:
    """Sync function - called inside async context."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,          # Detect column type changes
        compare_server_default=True,    # Detect default value changes
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine and run migrations."""
    configuration = alembic_config.get_section(alembic_config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,    # NullPool: each migration uses 1 connection and then closes
    )

    async with connectable.connect() as connection:
        # run_sync bridges between async connection and sync Alembic context
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()