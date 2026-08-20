"""Integration test fixtures — real DB, fake Twilio.

`clean_auth_tables` truncates the four auth tables before each test so
state from one test doesn't leak into the next. We can't use the
transactional rollback pattern from tests/conftest.py here because the
FastAPI app commits on a different connection than the sync test
session.

`sms_fake` swaps the process-wide Twilio client out for a fresh
InMemoryTwilioClient that the test can inspect.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator, Generator
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.bvn import InMemoryBvnVerifier
from app.adapters.document_storage import InMemoryDocumentStorage
from app.adapters.email_verification import InMemoryEmailClient
from app.adapters.nin import InMemoryNinVerifier
from app.adapters.twilio import InMemoryTwilioClient
from app.config import get_settings
from app.db import dispose_engine

# Match the auth tables the migrations create, in FK-safe order.
_TABLES = (
    "audit_log",
    "refresh_tokens",
    "auth_credentials",
    "buyer_profiles",
    "email_verification_tokens",
    "otp_codes",
    "user_pii",
    "users",
)


@pytest.fixture
def clean_auth_tables(db_engine: Engine) -> Generator[None, None, None]:
    """TRUNCATE all auth tables before the test runs."""
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


# Outbound adapters that must never dial out from a test, with the setting
# that forces each to its in-memory fake. Settings read maiplot/.env, and a
# developer running a real e2e check will have flipped some of these to
# false there (see otp-e2e-test-plan.md) — without this pin those creds leak
# into the test run and it makes real API calls. That is not hypothetical:
# it sent live Twilio requests during SCRUM-175 until this was added.
_FORCED_FAKE_SETTINGS = (
    "TWILIO_USE_FAKE",
    "EMAIL_VERIFICATION_USE_FAKE",
    "BVN_USE_FAKE",
    "NIN_USE_FAKE",
    "POA_STORAGE_USE_FAKE",
)


def _reset_adapter_singletons() -> None:
    """Clear dependencies.py's memoised adapter clients."""
    from app import dependencies

    for attr in ("_sms_client", "_email_sender", "_bvn_verifier", "_nin_verifier"):
        if hasattr(dependencies, attr):
            setattr(dependencies, attr, None)


@pytest.fixture(autouse=True)
def _force_async_database_url() -> Generator[None, None, None]:
    """Pin the app's async engine to the same DB the test session uses, and
    force every outbound adapter to its fake.

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

    originals = {key: os.environ.get(key) for key in _FORCED_FAKE_SETTINGS}
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    for key in _FORCED_FAKE_SETTINGS:
        os.environ[key] = "true"
    get_settings.cache_clear()
    # dependencies.py memoises each adapter in a module-level global, so a
    # client built before the pin (or by an earlier test) would survive the
    # settings cache_clear. Drop them so the next get_* rebuilds from the
    # pinned env.
    _reset_adapter_singletons()
    yield
    if original is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original
    for key, value in originals.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def sms_fake() -> AsyncIterator[InMemoryTwilioClient]:
    """Bind a fresh InMemoryTwilioClient for the duration of the test."""
    from app.dependencies import get_sms_client
    from app.main import app

    fake = InMemoryTwilioClient()
    app.dependency_overrides[get_sms_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_sms_client, None)


@pytest_asyncio.fixture
async def email_verification_fake() -> AsyncIterator[InMemoryEmailClient]:
    """Bind a fresh InMemoryEmailClient so verification emails are captured
    in-process (SCRUM-152) instead of hitting Resend."""
    from app.dependencies import get_email_sender
    from app.main import app

    fake = InMemoryEmailClient()
    app.dependency_overrides[get_email_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_email_sender, None)


def extract_email_token(verify_url: str) -> str:
    """Pull the magic-link token out of a captured verification URL."""
    tokens = parse_qs(urlparse(verify_url).query).get("token")
    assert tokens, f"no token in verify url: {verify_url!r}"
    return tokens[0]


def extract_otp_code(message: str) -> str:
    """Pull the 6-digit OTP out of a captured SMS body.

    The plaintext code is never returned by the API and never logged — the
    captured SMS is the only place a test can read it, exactly as in
    production (CLAUDE.md §4)."""
    match = re.search(r"\b(\d{6})\b", message)
    assert match, f"no 6-digit code in sms: {message!r}"
    return match.group(1)


async def register_only(
    http_client: AsyncClient,
    *,
    phone: str = "08012345678",
    role: str = "buyer",
    email: str = "user@example.com",
    password: str | None = None,
    seller_authority_type: str | None = None,
) -> dict[str, Any]:
    """POST /auth/register and assert a 201; return the response body.

    Split out of register_and_verify for tests that need an account left in
    the `unverified` state (the email-resend path, for instance)."""
    payload: dict[str, Any] = {"phone": phone, "role": role, "email": email}
    if password is not None:
        payload["password"] = password
    if seller_authority_type is not None:
        payload["seller_authority_type"] = seller_authority_type
    reg = await http_client.post("/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    body: dict[str, Any] = reg.json()
    return body


async def register_and_verify(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    *,
    phone: str = "08012345678",
    role: str = "buyer",
    email: str = "user@example.com",
    password: str | None = None,
    seller_authority_type: str | None = None,
) -> dict[str, Any]:
    """Register a user then confirm the OTP from the captured SMS; return the
    /auth/otp/verify response body (access_token, refresh_token, user{...}).

    SCRUM-175 pointed this back at the phone-OTP path. The response shape is
    identical to /auth/verify/email's, so callers were unaffected."""
    await register_only(
        http_client,
        phone=phone,
        role=role,
        email=email,
        password=password,
        seller_authority_type=seller_authority_type,
    )

    code = extract_otp_code(sms.sent[-1].message)
    verify = await http_client.post(
        "/auth/otp/verify", json={"phone": phone, "otp": code, "purpose": "registration"}
    )
    assert verify.status_code == 200, verify.text
    body: dict[str, Any] = verify.json()
    return body


@pytest_asyncio.fixture
async def bvn_fake() -> AsyncIterator[InMemoryBvnVerifier]:
    """Bind a fresh InMemoryBvnVerifier (defaults to a 'verified' outcome)."""
    from app.dependencies import get_bvn_verifier
    from app.main import app

    fake = InMemoryBvnVerifier()
    app.dependency_overrides[get_bvn_verifier] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_bvn_verifier, None)


@pytest_asyncio.fixture
async def nin_fake() -> AsyncIterator[InMemoryNinVerifier]:
    """Bind a fresh InMemoryNinVerifier (defaults to a 'verified' outcome)."""
    from app.dependencies import get_nin_verifier
    from app.main import app

    fake = InMemoryNinVerifier()
    app.dependency_overrides[get_nin_verifier] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_nin_verifier, None)


@pytest_asyncio.fixture
async def storage_fake() -> AsyncIterator[InMemoryDocumentStorage]:
    """Bind a fresh InMemoryDocumentStorage so PoA tests never touch S3."""
    from app.dependencies import get_document_storage
    from app.main import app

    fake = InMemoryDocumentStorage()
    app.dependency_overrides[get_document_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_document_storage, None)


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
