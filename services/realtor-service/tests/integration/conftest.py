"""Integration test fixtures — real DB, real JWT.

realtor-service owns the realtors/inspections tables but references users from
the shared DB, so tests seed users directly (sync db_engine) and mint a real
access token with the same secret/issuer the app verifies with. Loaded by path
to avoid the cross-service `tests.integration.conftest` name collision.
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

from app.adapters.registration_number import InMemoryRegistrationNumberIssuer
from app.config import get_settings
from app.db import dispose_engine

# FK-safe truncation order (CASCADE covers the rest).
_TABLES = (
    "realtors",
    "inspections",
    "commissions",
    "audit_log",
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
    def _seed(*, role: str = "realtor") -> UUID:
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
def seed_realtor(db_engine: Engine) -> Callable[..., UUID]:
    """Seed a user + a realtors row in the given approval_status."""

    def _seed(
        *,
        status: str = "pending",
        esvarbon: str | None = None,
        full_name: str | None = None,
    ) -> UUID:
        user_id = uuid4()
        # esvarbon_number is UNIQUE — default to a distinct value per seed. New
        # realtors get NULL here (SCRUM-207); seeds keep supplying one so the
        # read-side "historic licence still shows" behaviour stays covered.
        esvarbon = esvarbon or f"ESV/{uuid4().hex[:8].upper()}"
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, 'realtor', 'id_verified', TRUE)"
                ),
                {"id": user_id},
            )
            if full_name is not None:
                # The admin queue reads the applicant's name from user_pii
                # (SCRUM-207). phone is UNIQUE, so derive a distinct one.
                conn.execute(
                    text(
                        "INSERT INTO user_pii (user_id, phone, full_name) "
                        "VALUES (:id, :phone, :name)"
                    ),
                    {
                        "id": user_id,
                        "phone": f"+23480{uuid4().int % 10**8:08d}",
                        "name": full_name,
                    },
                )
            conn.execute(
                text(
                    "INSERT INTO realtors (id, esvarbon_number, coverage_states, "
                    "government_id_s3_key, approval_status) "
                    "VALUES (:id, :esv, ARRAY['Lagos'], 'realtor-id/x.pdf', :status)"
                ),
                {"id": user_id, "esv": esvarbon, "status": status},
            )
        return user_id

    return _seed


@pytest_asyncio.fixture(autouse=True)
async def registration_number_fake() -> AsyncIterator[InMemoryRegistrationNumberIssuer]:
    """Bind a fresh in-memory registration-number issuer for every test.

    autouse and unconditional: approving a realtor calls auth-service (SCRUM-207),
    and a test must never depend on that service running — nor on the
    `registration_number_use_fake` default surviving a stray .env, which is
    exactly how an integration suite ends up making real HTTP calls.

    Set `.fail_next = True` to exercise the fail-closed 503.
    """
    from app.dependencies import get_registration_number_issuer
    from app.main import app

    fake = InMemoryRegistrationNumberIssuer()
    app.dependency_overrides[get_registration_number_issuer] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_registration_number_issuer, None)


@pytest.fixture
def auth_header() -> Callable[[str], dict[str, str]]:
    def _header(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _header
