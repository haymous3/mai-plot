"""Integration test fixtures — real DB, real JWT, fake storage.

document-service verifies listing ownership by reading the shared
property_listings + users tables, so the tests seed those directly and mint a
real access token. Helpers are FIXTURES (not module functions) to avoid the
cross-service `tests` package collision (every service has a
tests.integration package; `import tests...` resolves to the alphabetically
first service).
"""

from __future__ import annotations

import asyncio
import os
import sys
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

# psycopg's async mode refuses to run on Windows' default ProactorEventLoop.
# Selecting the psycopg escape hatch therefore also has to select a compatible
# loop policy, at import time — before pytest-asyncio creates any loop.
# Mirrors auth-service's conftest (SCRUM-188).
if os.environ.get("TEST_DB_DRIVER") == "psycopg" and sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.db import dispose_engine

# FK-safe order; CASCADE handles the property_listings partitions.
_TABLES = (
    "audit_log",
    "offers",
    "listing_documents",
    "loan_documents",
    "user_documents",
    "loans",
    "bank_partners",
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
    # asyncpg on Windows intermittently drops the connection mid-suite with
    # "WinError 64: The specified network name is no longer available", failing
    # every DB-touching test for reasons unrelated to the code under test.
    # psycopg3 does not, so a developer on Windows can run the suite with
    # TEST_DB_DRIVER=psycopg. CI keeps the default and exercises asyncpg, which
    # is what production uses — this is a local escape hatch, not a swap.
    driver = os.environ.get("TEST_DB_DRIVER", "asyncpg")
    async_url = f"postgresql+{driver}://{user}:{password}@localhost:{port}/{db}"
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


@pytest_asyncio.fixture
async def doc_storage_fake() -> AsyncIterator[Any]:
    """Bind a fresh InMemoryDocumentStorage so each test starts clean."""
    from app.adapters.document_storage import InMemoryDocumentStorage
    from app.dependencies import get_document_storage
    from app.main import app

    fake = InMemoryDocumentStorage()
    app.dependency_overrides[get_document_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_document_storage, None)


@pytest.fixture
def mint_access_token() -> Callable[[UUID, str], str]:
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
    def _seed(*, phone: str, role: str = "seller") -> UUID:
        user_id = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": user_id, "role": role},
            )
            conn.execute(
                text(
                    "INSERT INTO user_pii (user_id, phone, full_name) "
                    "VALUES (:id, :phone, 'Seller')"
                ),
                {"id": user_id, "phone": phone},
            )
        return user_id

    return _seed


@pytest.fixture
def seed_listing(db_engine: Engine) -> Callable[..., UUID]:
    def _seed(*, seller_id: UUID, status: str = "pending_review") -> UUID:
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
def seed_document(db_engine: Engine) -> Callable[..., UUID]:
    def _seed(
        *,
        listing_id: UUID,
        document_type: str = "c_of_o",
        status: str = "pending",
    ) -> UUID:
        document_id = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO listing_documents
                        (id, listing_id, document_type, s3_key, verification_status)
                    VALUES (:id, :lid, :dtype, :s3, :status)
                    """
                ),
                {
                    "id": document_id,
                    "lid": listing_id,
                    "dtype": document_type,
                    "s3": f"listings/{listing_id}/documents/{document_id}.pdf",
                    "status": status,
                },
            )
        return document_id

    return _seed


@pytest.fixture
def seed_offer(db_engine: Engine) -> Callable[..., None]:
    """Insert an offer (the access relationship that lets a buyer view docs)."""

    def _seed(*, listing_id: UUID, buyer_id: UUID, status: str = "pending") -> None:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO offers
                        (listing_id, buyer_id, offered_price_kobo, status, expires_at)
                    VALUES (:lid, :uid, 1000000000, :status, NOW() + INTERVAL '7 days')
                    """
                ),
                {"lid": listing_id, "uid": buyer_id, "status": status},
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
