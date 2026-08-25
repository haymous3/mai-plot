"""Per-service pytest fixtures shared across every Maihomme service.

Same file copied verbatim into each service. Promote to a `_shared`
workspace member when the duplication actually hurts; for now CLAUDE.md
keeps services independent.

Fixtures:
  * db_engine    — session-scoped sync engine via psycopg. Skips DB-bound
                   tests cleanly if Postgres is unreachable.
  * db_session   — function-scoped sync session wrapped in a transaction
                   that rolls back on teardown (no commits leak).
  * client       — fastapi.testclient.TestClient(app), for sync tests.
  * async_client — httpx.AsyncClient(transport=ASGITransport(app=app)),
                   for async tests.
  * redis_client — redis.asyncio.Redis. Skips if Redis unreachable.

Tests that don't request the DB/Redis fixtures (e.g. the existing
/health smoke) run fine without those services up.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Generator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def _test_database_url() -> str:
    """Build a sync (psycopg) DATABASE_URL for host-side tests.

    Tests always run from the host (CI runner or dev machine), so we
    force localhost — POSTGRES_HOST in .env names the Docker compose
    service ('postgres') which only resolves inside the container
    network. POSTGRES_HOST_PORT respects .env so the local dev override
    (5434 because port 5432 is taken by another local Postgres) still
    works; CI runs without .env and gets the 5432 default."""
    port = os.environ.get("POSTGRES_HOST_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "maiplot")
    password = os.environ.get("POSTGRES_PASSWORD", "change-me-local")
    db = os.environ.get("POSTGRES_DB", "maiplot")
    return f"postgresql+psycopg://{user}:{password}@localhost:{port}/{db}"


def _redis_url() -> str:
    """Tests always hit Redis via localhost for the same reason."""
    port = os.environ.get("REDIS_HOST_PORT", "6379")
    return f"redis://localhost:{port}/0"


@pytest.fixture(scope="session")
def db_engine() -> Generator[Engine, None, None]:
    """Sync SQLAlchemy engine. Skips the whole test if Postgres is down."""
    engine = create_engine(_test_database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"Postgres not reachable for tests: {exc}")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Function-scoped session wrapped in a transaction that always rolls
    back. Keeps tests isolated and the schema clean between runs."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client() -> TestClient:
    """Sync test client. Imports app lazily so fixture creation does not
    trigger module-load side effects for tests that don't need it."""
    from app.main import app

    return TestClient(app)


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """Async httpx client wrapping the ASGI app — for endpoints that need
    real async test execution (DB calls, awaited middleware, etc.)."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Any]:
    """Async Redis client. Skips the test if Redis is unreachable."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(_redis_url(), decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        pytest.skip(f"Redis not reachable for tests: {exc}")
    try:
        yield client
    finally:
        await client.aclose()
