"""Integration test fixtures — real DB, real JWT.

transaction-service reads property_listings + users from the shared DB, so the
tests seed those rows directly (sync db_engine) and mint a real access token
with the same secret/issuer the app verifies with. Loaded by path to avoid the
cross-service `tests.integration.conftest` name collision.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.db import dispose_engine

# FK-safe truncation order (CASCADE covers the rest).
_TABLES = (
    "offers",
    "escrow_ledger",
    "payment_events",
    "transaction_events",
    "transactions",
    "property_listings",
    "user_pii",
    "users",
)


@pytest.fixture
def clean_tables(db_engine: Engine) -> Generator[None, None, None]:
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def _force_async_database_url() -> Generator[None, None, None]:
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
async def http_client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await dispose_engine()


@pytest.fixture
def mint_token() -> Callable[[UUID, str], str]:
    def _mint(user_id: UUID, role: str) -> str:
        settings = get_settings()
        now = datetime.now(UTC)
        payload = {
            "iss": settings.jwt_issuer,
            "sub": str(user_id),
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "type": "access",
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    return _mint


@pytest.fixture
def seed_user(db_engine: Engine) -> Callable[..., UUID]:
    def _seed(*, role: str = "buyer") -> UUID:
        user_id = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": user_id, "role": role},
            )
        return user_id

    return _seed


@pytest.fixture
def seed_listing(db_engine: Engine) -> Callable[..., UUID]:
    def _seed(*, seller_id: UUID, status: str = "active") -> UUID:
        listing_id = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO property_listings
                        (id, seller_id, property_type, title, address_text, location,
                         lga, state, asking_price_kobo, sale_type, status)
                    VALUES
                        (:id, :sid, 'land', 'Plot', '1 Demo St',
                         ST_SetSRID(ST_MakePoint(3.4, 6.5), 4326)::geography,
                         'Ikeja', 'Lagos', 5000000000, 'normal', :status)
                    """
                ),
                {"id": listing_id, "sid": seller_id, "status": status},
            )
        return listing_id

    return _seed


@pytest.fixture
def auth_header() -> Callable[[str], dict[str, str]]:
    def _header(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _header
