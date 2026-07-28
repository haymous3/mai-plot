"""Alembic environment — async, per-service version table.

DATABASE_URL is read from the environment so the same migration runs against
dev (docker compose), test, staging, and prod without code changes. The
version table name comes from `service_name` in alembic.ini so each service
has its own migration history while sharing one PostgreSQL database.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set; alembic needs it to connect to PostgreSQL.")
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Service identity is declared in alembic.ini, NOT derived from the directory
# name. The Dockerfile copies migrations/ to /app/migrations/, so a path-based
# derivation resolves to "app" inside every container and silently collapses all
# eight migration histories into one shared version table — one service then
# reads another's revision id as its own. alembic.ini ships per service in the
# image, so it is the one identity that survives the copy.
SERVICE_NAME = (config.get_main_option("service_name") or "").strip()
if not SERVICE_NAME:
    raise RuntimeError(
        "service_name is not set in alembic.ini; without it every service would "
        "share the alembic_version table and corrupt each other's history."
    )
VERSION_TABLE = f"alembic_version_{SERVICE_NAME.replace('-', '_')}"

# Raw SQL migrations via op.execute() and op.create_table() — no SQLAlchemy
# ORM models are imported, so target_metadata stays None.
target_metadata = None


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section: dict[str, Any] = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = DATABASE_URL
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
