"""Integration test fixtures — real DB, real JWT.

loan-service owns loans/bank_partners but reads transactions + users from the
shared DB, so tests seed those directly (sync db_engine) and mint a real access
token with the same secret/issuer the app verifies with.
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
_TABLES = ("loans", "loan_repayment_milestones", "bank_partners", "transactions", "users")


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
def auth_header() -> Callable[[str], dict[str, str]]:
    def _header(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _header


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
def seed_transaction(db_engine: Engine) -> Callable[..., UUID]:
    def _seed(*, buyer_id: UUID, agreed_price_kobo: int = 800_000_000) -> UUID:
        tx_id = uuid4()
        seller = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, 'seller', 'id_verified', TRUE)"
                ),
                {"id": seller},
            )
            conn.execute(
                text(
                    "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                    "agreed_price_kobo, stage) VALUES "
                    "(:id, :lid, :bid, :sid, :price, 'inspection_completed')"
                ),
                {
                    "id": tx_id,
                    "lid": uuid4(),
                    "bid": buyer_id,
                    "sid": seller,
                    "price": agreed_price_kobo,
                },
            )
        return tx_id

    return _seed


@pytest.fixture
def seed_bank_partner(db_engine: Engine) -> Callable[..., UUID]:
    def _seed(*, is_active: bool = True) -> UUID:
        pid = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bank_partners
                        (id, name, short_code, loan_min_kobo, loan_max_kobo,
                         interest_rate_bps, min_tenure_months, max_tenure_months, is_active)
                    VALUES (:id, 'Test Bank', :code, 1000000, 500000000, 2200, 6, 36, :active)
                    """
                ),
                {"id": pid, "code": f"BANK{uuid4().hex[:6].upper()}", "active": is_active},
            )
        return pid

    return _seed
