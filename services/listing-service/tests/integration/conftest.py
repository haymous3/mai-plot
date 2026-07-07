"""Integration test fixtures — real DB, real JWT.

listing-service reads seller eligibility from the shared auth tables, so the
tests seed `users` + `user_pii` rows directly (via the sync db_engine) and
mint a real access token with the same secret/issuer the app verifies with.

Helpers are exposed as FIXTURES (not module-level functions) deliberately:
every service has a `tests.integration.conftest`, and `import tests...`
resolves to the alphabetically-first service's copy (auth-service), not this
one. Fixtures are loaded by path, so they avoid that cross-service collision.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.db import dispose_engine

# Tables this service's tests touch, in FK-safe order (CASCADE handles the
# property_listings partitions and any users-referencing rows).
_TABLES = ("audit_log", "saved_listings", "listing_media", "property_listings", "user_pii", "users")


@pytest.fixture
def clean_listing_tables(db_engine: Engine) -> Generator[None, None, None]:
    """TRUNCATE listing + seeded auth tables before the test runs."""
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def _force_async_database_url() -> Generator[None, None, None]:
    """Pin the app's async engine to the same DB the sync test session uses
    (localhost + POSTGRES_HOST_PORT), mirroring auth-service's fixture."""
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
    """Async httpx client targeting the in-process FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await dispose_engine()


@pytest_asyncio.fixture
async def media_storage_fake() -> AsyncIterator[Any]:
    """Bind a fresh InMemoryMediaStorage so each media test starts clean and
    can inspect what was stored (the process-wide default is cached)."""
    from app.adapters.media_storage import InMemoryMediaStorage
    from app.dependencies import get_media_storage
    from app.main import app

    fake = InMemoryMediaStorage(cdn_domain="cdn.maiplot.test")
    app.dependency_overrides[get_media_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_media_storage, None)


@pytest_asyncio.fixture
async def search_index_fake() -> AsyncIterator[Any]:
    """Bind a fresh InMemorySearchIndex so search tests start clean and can
    seed/inspect indexed docs directly (the process-wide default is cached)."""
    from app.adapters.search_index import InMemorySearchIndex
    from app.dependencies import get_search_index
    from app.main import app

    fake = InMemorySearchIndex()
    app.dependency_overrides[get_search_index] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_search_index, None)


@pytest_asyncio.fixture
async def disable_cache() -> AsyncIterator[None]:
    """Force the feed/detail endpoints to bypass Redis and read Postgres, so
    integration assertions are deterministic whether or not CI's Redis is up.
    The caching path itself is covered by the get_with_fallback unit tests."""
    from app.dependencies import get_redis
    from app.main import app

    app.dependency_overrides[get_redis] = lambda: None
    yield
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def mint_access_token() -> Callable[[UUID, str], str]:
    """Return a helper that mints an access token the app will accept (same
    secret/issuer/shape as auth-service issues)."""

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
def seed_seller(db_engine: Engine) -> Callable[..., UUID]:
    """Return a helper that inserts a users + user_pii row and returns its id."""

    def _seed(
        *,
        phone: str,
        role: str = "seller",
        seller_authority_type: str | None = "owner",
        poa_verified_status: str = "not_applicable",
        verified_status: str = "id_verified",
        with_identity: bool = True,
    ) -> UUID:
        user_id = uuid4()
        # A bcrypt-shaped placeholder is enough — the gate only checks presence.
        bvn_hash = "$2b$12$fakehashforidentitypresencecheck0000000000" if with_identity else None
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, role, verified_status, seller_authority_type,
                                       poa_verified_status, is_active)
                    VALUES (:id, :role, :vs, :auth, :poa, TRUE)
                    """
                ),
                {
                    "id": user_id,
                    "role": role,
                    "vs": verified_status,
                    "auth": seller_authority_type,
                    "poa": poa_verified_status,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO user_pii (user_id, phone, full_name, bvn_hash)
                    VALUES (:id, :phone, :name, :bvn)
                    """
                ),
                {"id": user_id, "phone": phone, "name": "Test Seller", "bvn": bvn_hash},
            )
        return user_id

    return _seed


@pytest.fixture
def seed_listing(db_engine: Engine) -> Callable[..., UUID]:
    """Insert a property_listings row directly and return its id."""

    def _seed(
        *,
        seller_id: UUID,
        state: str = "Lagos",
        lga: str = "Ikeja",
        sale_type: str = "normal",
        status: str = "active",
        asking_price_kobo: int = 5_000_000_000,
        property_type: str = "land",
        title: str = "Test Plot",
        urgency_tag: str | None = None,
        doc_verification_status: str = "not_submitted",
        lat: float = 6.5,
        lng: float = 3.4,
    ) -> UUID:
        listing_id = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO property_listings
                        (id, seller_id, property_type, title, address_text, location,
                         lga, state, asking_price_kobo, sale_type, urgency_tag, status,
                         doc_verification_status)
                    VALUES
                        (:id, :sid, :ptype, :title, :addr,
                         ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                         :lga, :state, :price, :stype, :urg, :status, :doc)
                    """
                ),
                {
                    "id": listing_id,
                    "sid": seller_id,
                    "ptype": property_type,
                    "title": title,
                    "addr": "1 Demo St, Lagos",
                    "lng": lng,
                    "lat": lat,
                    "lga": lga,
                    "state": state,
                    "price": asking_price_kobo,
                    "stype": sale_type,
                    "urg": urgency_tag,
                    "status": status,
                    "doc": doc_verification_status,
                },
            )
        return listing_id

    return _seed


@pytest.fixture
def seed_media(db_engine: Engine) -> Callable[..., None]:
    """Insert a listing_media row for a listing."""

    def _seed(
        *,
        listing_id: UUID,
        media_type: str = "photo",
        cdn_url: str = "https://cdn.maiplot.ng/x.jpg",
        sort_order: int = 0,
    ) -> None:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO listing_media (listing_id, media_type, s3_key, cdn_url, sort_order)
                    VALUES (:lid, :mtype, :s3, :cdn, :sort)
                    """
                ),
                {
                    "lid": listing_id,
                    "mtype": media_type,
                    "s3": "media/x.jpg",
                    "cdn": cdn_url,
                    "sort": sort_order,
                },
            )

    return _seed


@pytest.fixture
def auth_header() -> Callable[[str], dict[str, str]]:
    def _header(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _header


@pytest.fixture
def assert_error_envelope() -> Callable[[dict[str, Any], str], None]:
    def _assert(body: dict[str, Any], expected_code: str) -> None:
        assert body["error_code"] == expected_code
        assert "message" in body
        assert "details" in body

    return _assert
