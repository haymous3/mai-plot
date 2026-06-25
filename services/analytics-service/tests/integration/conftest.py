"""Integration test fixtures — real DB, real JWT.

analytics-service reads the shared audit_log table (owned by its own migration
0001). Tests seed audit_log + users directly (sync db_engine) and mint a real
access token with the same secret/issuer the app verifies with. Loaded by path
to avoid the cross-service `tests.integration.conftest` name collision.
"""

from __future__ import annotations

import json
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

# audit_log references users(id); TRUNCATE both (CASCADE covers the rest).
# TRUNCATE (not DELETE) bypasses the append-only BEFORE DELETE trigger.
_TABLES = ("audit_log", "users")


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
    def _seed(*, role: str = "admin") -> UUID:
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
def seed_audit(db_engine: Engine) -> Callable[..., UUID]:
    """Insert one audit_log row. created_at is explicit so ordering tests are
    deterministic (NOW() is constant within a transaction)."""

    def _seed(
        *,
        action: str = "listing.approved",
        entity_type: str = "listing",
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_role: str | None = "admin",
        new_value: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> UUID:
        audit_id = uuid4()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO audit_log
                        (id, actor_id, actor_role, action, entity_type, entity_id,
                         new_value, ip_address, user_agent, created_at)
                    VALUES
                        (:id, :actor, :role, :action, :etype, :eid,
                         CAST(:new AS jsonb), :ip, :ua, :created)
                    """
                ),
                {
                    "id": audit_id,
                    "actor": actor_id,
                    "role": actor_role,
                    "action": action,
                    "etype": entity_type,
                    "eid": entity_id or uuid4(),
                    "new": json.dumps(new_value) if new_value is not None else None,
                    "ip": "127.0.0.1",
                    "ua": "pytest",
                    "created": created_at or datetime.now(UTC),
                },
            )
        return audit_id

    return _seed
