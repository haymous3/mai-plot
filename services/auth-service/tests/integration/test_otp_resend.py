"""POST /auth/otp/resend + the failed-attempt cap (SCRUM-176).

Two things are exercised here that only a real DB can show: that a resend
genuinely supersedes the previous code row, and that the cap burns a code
in the database rather than merely refusing the request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.twilio import InMemoryTwilioClient
from app.services.rate_limit import RateLimitResult
from tests.integration.conftest import assert_error_envelope, extract_otp_code, register_only

_PHONE_LOCAL = "08012345678"
_PHONE = "+2348012345678"
_EMAIL = "buyer@example.com"


def _otp_rows(db_engine: Engine) -> list[tuple[str, bool]]:
    """(code_hash, is_used) for this phone, oldest first."""
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT code_hash, used_at IS NOT NULL AS used FROM otp_codes "
                "WHERE phone = :phone ORDER BY created_at"
            ),
            {"phone": _PHONE},
        ).all()
    return [(r.code_hash, r.used) for r in rows]


@pytest.mark.asyncio
async def test_resend_supersedes_the_previous_code(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)
    first_code = extract_otp_code(sms_fake.sent[-1].message)

    resp = await http_client.post("/auth/otp/resend", json={"phone": _PHONE_LOCAL})
    assert resp.status_code == 202, resp.text

    second_code = extract_otp_code(sms_fake.sent[-1].message)
    assert len(sms_fake.sent) == 2

    rows = _otp_rows(db_engine)
    assert len(rows) == 2
    assert rows[0][1] is True, "the registration code should have been burnt"
    assert rows[1][1] is False, "the resent code should be the live one"

    # The superseded code must no longer verify, even inside its 5-min window.
    stale = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": first_code, "purpose": "registration"},
    )
    assert stale.status_code == 401
    assert_error_envelope(stale.json(), "OTP_INVALID")

    fresh = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": second_code, "purpose": "registration"},
    )
    assert fresh.status_code == 200, fresh.text


@pytest.mark.asyncio
async def test_resend_unknown_number_is_generic_202_and_sends_nothing(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/otp/resend", json={"phone": "08099999999"})
    assert resp.status_code == 202, resp.text
    # No account -> no SMS, but the same generic response (no enumeration).
    assert sms_fake.sent == []


@pytest.mark.asyncio
async def test_resend_already_verified_is_generic_202_and_sends_nothing(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)
    code = extract_otp_code(sms_fake.sent[-1].message)
    verified = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": code, "purpose": "registration"},
    )
    assert verified.status_code == 200

    resp = await http_client.post("/auth/otp/resend", json={"phone": _PHONE_LOCAL})
    assert resp.status_code == 202, resp.text
    # Nothing beyond the original registration SMS.
    assert len(sms_fake.sent) == 1


@pytest.mark.asyncio
async def test_resend_matches_the_unknown_number_response_exactly(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """The whole point of the generic 202: a caller must not be able to tell a
    real unverified account from a number that has never registered."""
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)

    real = await http_client.post("/auth/otp/resend", json={"phone": _PHONE_LOCAL})
    unknown = await http_client.post("/auth/otp/resend", json={"phone": "08099999999"})

    assert real.status_code == unknown.status_code == 202
    assert real.json() == unknown.json()


@pytest.mark.asyncio
async def test_resend_invalid_phone_returns_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/otp/resend", json={"phone": "+15551234567"})
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
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    # The limit is checked before the user lookup, so no registered account is
    # needed to exercise the 429.
    resp = await http_client.post("/auth/otp/resend", json={"phone": _PHONE_LOCAL})
    assert resp.status_code == 429
    assert_error_envelope(resp.json(), "VERIFICATION_RATE_LIMITED")


# --- attempt cap -----------------------------------------------------------
#
# The limiter is bound deterministically for every integration test in
# conftest (`deterministic_otp_attempts`) — see the note there for why it must
# not touch Redis.


@pytest.mark.asyncio
async def test_wrong_code_reports_attempts_remaining(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """The verify-OTP screen shows "N attempts left", so the count has to come
    off the API rather than being guessed client-side."""
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)

    resp = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": "000000", "purpose": "registration"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert_error_envelope(body, "OTP_INVALID")
    assert body["details"]["attempts_remaining"] == 2


@pytest.mark.asyncio
async def test_cap_burns_the_code_and_returns_429(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """Three misses must retire the code in the DB — leaving a guessed-at code
    alive for the rest of its window is the weakness this closes."""
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)
    real_code = extract_otp_code(sms_fake.sent[-1].message)
    wrong = "000000" if real_code != "000000" else "111111"

    for _ in range(2):
        miss = await http_client.post(
            "/auth/otp/verify",
            json={"phone": _PHONE_LOCAL, "otp": wrong, "purpose": "registration"},
        )
        assert miss.status_code == 401

    third = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": wrong, "purpose": "registration"},
    )
    assert third.status_code == 429
    assert_error_envelope(third.json(), "OTP_TOO_MANY_ATTEMPTS")

    assert _otp_rows(db_engine)[0][1] is True, "the code should be burnt in the DB"

    # Even the CORRECT code is dead now — that is the point.
    correct = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": real_code, "purpose": "registration"},
    )
    assert correct.status_code == 401
    assert_error_envelope(correct.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_resend_after_lockout_restores_a_working_code(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """The escape hatch the UI promises: "send a new code" gets you out of a
    lockout, on a fresh allowance."""
    await register_only(http_client, phone=_PHONE_LOCAL, role="buyer", email=_EMAIL)

    for _ in range(3):
        await http_client.post(
            "/auth/otp/verify",
            json={"phone": _PHONE_LOCAL, "otp": "000000", "purpose": "registration"},
        )

    resend = await http_client.post("/auth/otp/resend", json={"phone": _PHONE_LOCAL})
    assert resend.status_code == 202
    new_code = extract_otp_code(sms_fake.sent[-1].message)

    # The new code carries its OWN allowance — the counter is keyed on the OTP
    # row, so the spent one does not carry over. Checked before verifying,
    # because a used-up code would 401 for the wrong reason afterwards.
    miss = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": "000000", "purpose": "registration"},
    )
    assert miss.status_code == 401
    assert miss.json()["details"]["attempts_remaining"] == 2

    verified = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE_LOCAL, "otp": new_code, "purpose": "registration"},
    )
    assert verified.status_code == 200, verified.text
