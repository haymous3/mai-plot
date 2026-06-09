"""Integration test fixtures — real DB, fake Termii.

`clean_auth_tables` truncates the four auth tables before each test so
state from one test doesn't leak into the next. We can't use the
transactional rollback pattern from tests/conftest.py here because the
FastAPI app commits on a different connection than the sync test
session.

`override_termii` swaps the process-wide Termii client out for a fresh
InMemoryTermiiClient that the test can inspect.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Generator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.termii import InMemoryTermiiClient
from app.config import get_settings
from app.db import dispose_engine

# Match the auth tables the migration creates, in FK-safe order.
_TABLES = ("refresh_tokens", "otp_codes", "user_pii", "users")


@pytest.fixture
def clean_auth_tables(db_engine: Engine) -> Generator[None, None, None]:
    """TRUNCATE all auth tables before the test runs."""
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def _force_async_database_url() -> Generator[None, None, None]:
    """Pin the app's async engine to the same DB the test session uses.

    tests/conftest.py builds the sync URL from POSTGRES_HOST_PORT (so
    localhost works) but the app's Settings reads DATABASE_URL which
    defaults to the Docker hostname `postgres`. Override DATABASE_URL
    for the test process so the async engine reaches the same Postgres.
    """
    port = os.environ.get("POSTGRES_HOST_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "maiplot")
    password = os.environ.get("POSTGRES_PASSWORD", "change-me-local")
    db = os.environ.get("POSTGRES_DB", "maiplot")
    async_url = f"postgresql+asyncpg://{user}:{password}@localhost:{port}/{db}"
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    get_settings.cache_clear()
    yield
    if original is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def termii_fake() -> AsyncIterator[InMemoryTermiiClient]:
    """Bind a fresh InMemoryTermiiClient for the duration of the test."""
    from app.dependencies import get_termii
    from app.main import app

    fake = InMemoryTermiiClient()
    app.dependency_overrides[get_termii] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_termii, None)


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[AsyncClient]:
    """Async httpx client targeting the in-process FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await dispose_engine()


@pytest_asyncio.fixture
async def disable_rate_limit() -> AsyncIterator[None]:
    """Replace the rate limiter dependency with a passthrough.

    Most integration tests exercise the happy path or other failure modes
    and aren't trying to test the rate limiter. The dedicated rate-limit
    integration test opts out of this fixture.
    """
    from app.dependencies import _rate_limiter
    from app.main import app
    from app.services.rate_limit import OtpRateLimiter

    app.dependency_overrides[_rate_limiter] = lambda: OtpRateLimiter(None, max_per_hour=99)
    yield
    app.dependency_overrides.pop(_rate_limiter, None)


def assert_error_envelope(body: dict[str, Any], expected_code: str) -> None:
    """Reusable assertion for the api-contracts.md error envelope shape."""
    assert body["error_code"] == expected_code
    assert "message" in body
    assert "details" in body
