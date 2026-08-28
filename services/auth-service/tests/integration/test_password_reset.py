"""POST /auth/password/forgot + /auth/password/reset integration tests (SCRUM-191).

The forgot endpoint's whole contract is that its response carries no
information: a registered address and an unregistered one must produce
byte-identical bodies and the same status. Several tests here exist only to
hold that line, because the natural way to write the endpoint — a 404 for an
unknown address — is an account-enumeration oracle.
"""

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
_PASSWORD = "OriginalPass1"
_NEW_PASSWORD = "BrandNewPass9"


async def _register(
    http_client: AsyncClient,
    *,
    email: str = _EMAIL,
    phone: str = "08012345678",
    password: str | None = _PASSWORD,
) -> str:
    body: dict[str, object] = {
        "phone": phone,
        "role": "buyer",
        "email": email,
        "verification_channel": "email",
    }
    if password is not None:
        body["password"] = password
    resp = await http_client.post("/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    user_id: str = resp.json()["user_id"]
    return user_id


async def _reset_link_token(
    http_client: AsyncClient, fake: InMemoryEmailClient, email: str = _EMAIL
) -> str:
    resp = await http_client.post("/auth/password/forgot", json={"email": email})
    assert resp.status_code == 202, resp.text
    return extract_email_token(fake.sent_password_resets[-1].reset_url)


@pytest.mark.asyncio
async def test_forgot_sends_a_reset_link_for_a_known_address(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register(http_client)

    resp = await http_client.post("/auth/password/forgot", json={"email": _EMAIL})
    assert resp.status_code == 202, resp.text

    assert len(email_verification_fake.sent_password_resets) == 1
    assert email_verification_fake.sent_password_resets[0].to == _EMAIL
    assert extract_email_token(email_verification_fake.sent_password_resets[0].reset_url)

    with db_engine.connect() as conn:
        purpose = conn.execute(
            text(
                "SELECT purpose FROM email_verification_tokens "
                "WHERE user_id = :id AND purpose = 'password_reset'"
            ),
            {"id": user_id},
        ).scalar_one()
    assert purpose == "password_reset"


@pytest.mark.asyncio
async def test_forgot_response_is_identical_for_known_and_unknown_addresses(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)

    known = await http_client.post("/auth/password/forgot", json={"email": _EMAIL})
    unknown = await http_client.post("/auth/password/forgot", json={"email": "nobody@example.com"})

    # The enumeration guarantee: same status AND the same bytes.
    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content
    # Only the real address actually received anything.
    assert len(email_verification_fake.sent_password_resets) == 1


@pytest.mark.asyncio
async def test_forgot_supersedes_an_earlier_unused_link(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)

    first = await _reset_link_token(http_client, email_verification_fake)
    second = await _reset_link_token(http_client, email_verification_fake)
    assert first != second

    # The older link is dead the moment a newer one is minted, so a user cannot
    # leave a trail of live account keys in their inbox.
    stale = await http_client.post(
        "/auth/password/reset", json={"token": first, "new_password": _NEW_PASSWORD}
    )
    assert stale.status_code == 401
    assert_error_envelope(stale.json(), "RESET_TOKEN_INVALID")

    fresh = await http_client.post(
        "/auth/password/reset", json={"token": second, "new_password": _NEW_PASSWORD}
    )
    assert fresh.status_code == 200, fresh.text


@pytest.mark.asyncio
async def test_reset_replaces_the_password_and_logs_the_user_in_with_it(
    clean_auth_tables: None,
    disable_rate_limit: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)
    token = await _reset_link_token(http_client, email_verification_fake)

    resp = await http_client.post(
        "/auth/password/reset", json={"token": token, "new_password": _NEW_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sessions_revoked"] is True
    # No tokens in the body — the user is sent to /login, not signed in.
    assert "access_token" not in body
    assert "refresh_token" not in body

    old = await http_client.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert old.status_code == 401

    new = await http_client.post("/auth/login", json={"email": _EMAIL, "password": _NEW_PASSWORD})
    assert new.status_code == 200, new.text


@pytest.mark.asyncio
async def test_reset_gives_a_phone_only_account_its_first_password(
    clean_auth_tables: None,
    disable_rate_limit: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    # The class of user this ticket exists for: registered without a password,
    # so there is no auth_credentials row at all and /auth/set-password needs a
    # JWT they cannot obtain. Reset is their only way in.
    user_id = await _register(http_client, password=None)
    with db_engine.connect() as conn:
        before = conn.execute(
            text("SELECT count(*) FROM auth_credentials WHERE user_id = :id"),
            {"id": user_id},
        ).scalar_one()
    assert before == 0

    token = await _reset_link_token(http_client, email_verification_fake)
    resp = await http_client.post(
        "/auth/password/reset", json={"token": token, "new_password": _NEW_PASSWORD}
    )
    assert resp.status_code == 200, resp.text

    login = await http_client.post("/auth/login", json={"email": _EMAIL, "password": _NEW_PASSWORD})
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_reset_revokes_every_existing_session(
    clean_auth_tables: None,
    disable_rate_limit: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)
    login = await http_client.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    token = await _reset_link_token(http_client, email_verification_fake)
    await http_client.post(
        "/auth/password/reset", json={"token": token, "new_password": _NEW_PASSWORD}
    )

    # Whoever the user is locking out cannot ride an old refresh token past it.
    resp = await http_client.post("/auth/token/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reset_token_is_single_use(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register(http_client)
    token = await _reset_link_token(http_client, email_verification_fake)

    first = await http_client.post(
        "/auth/password/reset", json={"token": token, "new_password": _NEW_PASSWORD}
    )
    assert first.status_code == 200, first.text

    second = await http_client.post(
        "/auth/password/reset", json={"token": token, "new_password": "SecondTry7"}
    )
    assert second.status_code == 401
    assert_error_envelope(second.json(), "RESET_TOKEN_INVALID")

    with db_engine.connect() as conn:
        unused = conn.execute(
            text(
                "SELECT count(*) FROM email_verification_tokens "
                "WHERE user_id = :id AND purpose = 'password_reset' AND used_at IS NULL"
            ),
            {"id": user_id},
        ).scalar_one()
    assert unused == 0


@pytest.mark.asyncio
async def test_a_reset_token_cannot_be_spent_at_verify_email(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # /auth/verify/email issues a JWT pair on a valid token. A reset link must
    # not be redeemable there — the purpose is not in EmailVerifyPurpose, so
    # the schema rejects it, and the registration purpose finds no such row.
    await _register(http_client)
    token = await _reset_link_token(http_client, email_verification_fake)

    wrong_purpose = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "password_reset"}
    )
    assert wrong_purpose.status_code == 422

    as_registration = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )
    assert as_registration.status_code == 401
    assert_error_envelope(as_registration.json(), "EMAIL_TOKEN_INVALID")


@pytest.mark.asyncio
async def test_a_verification_token_cannot_be_spent_at_password_reset(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # The mirror of the test above. Registration on the email channel sends a
    # verification link; it must not double as a password-reset link.
    await _register(http_client)
    verification_token = extract_email_token(email_verification_fake.sent[-1].verify_url)

    resp = await http_client.post(
        "/auth/password/reset",
        json={"token": verification_token, "new_password": _NEW_PASSWORD},
    )
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "RESET_TOKEN_INVALID")


@pytest.mark.asyncio
async def test_reset_with_an_unknown_token_returns_401(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post(
        "/auth/password/reset", json={"token": "not-a-real-token", "new_password": _NEW_PASSWORD}
    )
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "RESET_TOKEN_INVALID")


@pytest.mark.asyncio
async def test_reset_with_a_weak_password_returns_422_and_keeps_the_link_alive(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)
    token = await _reset_link_token(http_client, email_verification_fake)

    weak = await http_client.post(
        "/auth/password/reset", json={"token": token, "new_password": "alllowercase"}
    )
    assert weak.status_code == 422
    assert_error_envelope(weak.json(), "PASSWORD_TOO_WEAK")

    # The link survives a rejected password — burning it would force a whole
    # new email over a typo.
    retry = await http_client.post(
        "/auth/password/reset", json={"token": token, "new_password": _NEW_PASSWORD}
    )
    assert retry.status_code == 200, retry.text


@pytest.mark.asyncio
async def test_reset_with_a_too_short_password_returns_422(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    # Caught by the schema's length floor before the service ever runs.
    resp = await http_client.post(
        "/auth/password/reset", json={"token": "whatever", "new_password": "Ab1"}
    )
    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_forgot_with_an_invalid_email_returns_422(
    clean_auth_tables: None,
    disable_reset_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/password/forgot", json={"email": "not-an-email"})
    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "VALIDATION_ERROR")


class _DenyingLimiter:
    async def check_and_record(self, key: str) -> RateLimitResult:
        return RateLimitResult(allowed=False, remaining=0)


@pytest_asyncio.fixture
async def disable_reset_rate_limit() -> AsyncIterator[None]:
    """Passthrough for the forgot-password limiter.

    Separate from `disable_rate_limit` because the two flows deliberately use
    different limiter dependencies — overriding one does not touch the other.
    """
    from app.dependencies import _reset_rate_limiter
    from app.main import app
    from app.services.rate_limit import OtpRateLimiter

    app.dependency_overrides[_reset_rate_limiter] = lambda: OtpRateLimiter(None, max_per_hour=99)
    yield
    app.dependency_overrides.pop(_reset_rate_limiter, None)


@pytest_asyncio.fixture
async def deny_reset_rate_limit() -> AsyncIterator[None]:
    from app.dependencies import _reset_rate_limiter
    from app.main import app

    app.dependency_overrides[_reset_rate_limiter] = lambda: _DenyingLimiter()
    yield
    app.dependency_overrides.pop(_reset_rate_limiter, None)


@pytest.mark.asyncio
async def test_forgot_rate_limited_returns_429(
    clean_auth_tables: None,
    deny_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # The limiter runs before the user lookup, so no account is needed here —
    # and that ordering is the point: an unknown address is throttled on the
    # same schedule as a real one, leaving no timing signal either.
    resp = await http_client.post("/auth/password/forgot", json={"email": _EMAIL})
    assert resp.status_code == 429
    assert_error_envelope(resp.json(), "PASSWORD_RESET_RATE_LIMITED")
    assert email_verification_fake.sent_password_resets == []


@pytest.mark.asyncio
async def test_verification_resend_does_not_spend_the_reset_budget(
    clean_auth_tables: None,
    disable_rate_limit: None,
    deny_reset_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # The two email-keyed flows hold separate budgets (separate Redis prefixes
    # and separate limiter dependencies). Here the reset limiter denies while
    # the verification one allows, and each endpoint answers on its own budget.
    await _register(http_client)

    resend = await http_client.post("/auth/verify/email/resend", json={"email": _EMAIL})
    assert resend.status_code == 202

    forgot = await http_client.post("/auth/password/forgot", json={"email": _EMAIL})
    assert forgot.status_code == 429
