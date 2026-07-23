"""POST /auth/verify/email/resend integration tests (SCRUM-154)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.email_verification import InMemoryEmailClient
from app.services.rate_limit import RateLimitResult
from tests.integration.conftest import assert_error_envelope, extract_email_token

_EMAIL = "buyer@example.com"


async def _register(
    http_client: AsyncClient, email: str = _EMAIL, phone: str = "08012345678"
) -> str:
    resp = await http_client.post(
        "/auth/register", json={"phone": phone, "role": "buyer", "email": email}
    )
    assert resp.status_code == 201, resp.text
    user_id: str = resp.json()["user_id"]
    return user_id


@pytest.mark.asyncio
async def test_resend_sends_a_fresh_link_and_supersedes_the_old(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register(http_client)
    assert len(email_verification_fake.sent) == 1  # the registration email

    resp = await http_client.post("/auth/verify/email/resend", json={"email": _EMAIL})
    assert resp.status_code == 202, resp.text

    # A second email went out, to the same address.
    assert len(email_verification_fake.sent) == 2
    assert email_verification_fake.sent[-1].to == _EMAIL
    assert extract_email_token(email_verification_fake.sent[-1].verify_url)

    with db_engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM email_verification_tokens WHERE user_id = :id"),
            {"id": user_id},
        ).scalar_one()
        unused = conn.execute(
            text(
                "SELECT count(*) FROM email_verification_tokens "
                "WHERE user_id = :id AND used_at IS NULL"
            ),
            {"id": user_id},
        ).scalar_one()
    # Two tokens exist, but only the new one is still valid (old superseded).
    assert total == 2
    assert unused == 1


@pytest.mark.asyncio
async def test_resend_unknown_email_is_generic_202_and_sends_nothing(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/verify/email/resend", json={"email": "nobody@example.com"})
    assert resp.status_code == 202, resp.text
    # No account -> no email, but the same generic response (no enumeration).
    assert email_verification_fake.sent == []


@pytest.mark.asyncio
async def test_resend_already_verified_is_generic_202_and_sends_nothing(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)
    token = extract_email_token(email_verification_fake.sent[0].verify_url)
    verify = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )
    assert verify.status_code == 200

    resp = await http_client.post("/auth/verify/email/resend", json={"email": _EMAIL})
    assert resp.status_code == 202, resp.text
    # Already verified -> no new email beyond the original registration one.
    assert len(email_verification_fake.sent) == 1


@pytest.mark.asyncio
async def test_resend_invalid_email_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/verify/email/resend", json={"email": "not-an-email"})
    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "VALIDATION_ERROR")


class _DenyingLimiter:
    async def check_and_record(self, key: str) -> RateLimitResult:
        return RateLimitResult(allowed=False, remaining=0)


@pytest_asyncio.fixture
async def deny_rate_limit() -> AsyncIterator[None]:
    """Force the rate limiter to deny — deterministic 429 without Redis."""
    from app.dependencies import _rate_limiter
    from app.main import app

    app.dependency_overrides[_rate_limiter] = lambda: _DenyingLimiter()
    yield
    app.dependency_overrides.pop(_rate_limiter, None)


@pytest.mark.asyncio
async def test_resend_rate_limited_returns_429(
    clean_auth_tables: None,
    deny_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # Rate-limit is checked before the user lookup, so no registered account is
    # needed to exercise the 429.
    resp = await http_client.post("/auth/verify/email/resend", json={"email": _EMAIL})
    assert resp.status_code == 429
    assert_error_envelope(resp.json(), "VERIFICATION_RATE_LIMITED")
