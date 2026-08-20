"""POST /auth/otp/verify integration tests.

SCRUM-175 pointed registration back at phone OTP, so these tests now drive
the real production path: register, read the code out of the captured SMS,
and verify it. They previously seeded an otp_codes row directly because
registration (on the SCRUM-152 email flow) emitted no OTP at all.

That matters for single-use in particular: with a seeded row *plus* the
registration row, a second verify would fall through to the registration
OTP and fail on a wrong code rather than on already-used — the assertion
would still pass while testing nothing. One row per phone keeps
`test_verify_already_used_returns_401` honest (CLAUDE.md §4).
"""

from __future__ import annotations

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.twilio import InMemoryTwilioClient
from app.config import get_settings
from tests.integration.conftest import assert_error_envelope, extract_otp_code, register_only

_PHONE = "+2348012345678"


async def _register(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    email: str = "buyer@example.com",
    phone: str = "08012345678",
) -> tuple[str, str]:
    """Register a user; return (user_id, the OTP from the sent SMS)."""
    body = await register_only(http_client, phone=phone, role="buyer", email=email)
    user_id: str = body["user_id"]
    return user_id, extract_otp_code(sms.sent[-1].message)


def _expire_otp(db_engine: Engine, *, phone: str = _PHONE) -> None:
    """Backdate the live OTP for `phone` so the verify path sees it expired."""
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE otp_codes SET expires_at = NOW() - INTERVAL '1 minute' "
                "WHERE phone = :phone AND used_at IS NULL"
            ),
            {"phone": phone},
        )


@pytest.mark.asyncio
async def test_verify_happy_path_issues_tokens(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id, code = await _register(http_client, sms_fake)

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": code, "purpose": "registration"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_expires_in"] == 15 * 60
    assert body["user"]["id"] == user_id
    assert body["user"]["role"] == "buyer"
    assert body["user"]["verified_status"] == "phone_verified"

    settings = get_settings()
    payload = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert payload["iss"] == settings.jwt_issuer
    assert payload["sub"] == user_id
    assert payload["role"] == "buyer"

    with db_engine.connect() as conn:
        used = conn.execute(
            text("SELECT count(*) FROM otp_codes WHERE phone = :phone AND used_at IS NOT NULL"),
            {"phone": _PHONE},
        ).scalar_one()
        assert used == 1

        rt_count = conn.execute(
            text("SELECT count(*) FROM refresh_tokens WHERE user_id = :id"),
            {"id": user_id},
        ).scalar_one()
        assert rt_count == 1

        verified = conn.execute(
            text("SELECT verified_status FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar_one()
        assert verified == "phone_verified"


@pytest.mark.asyncio
async def test_registration_persists_only_the_hash(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """The plaintext code must never reach the database (CLAUDE.md §4)."""
    _, code = await _register(http_client, sms_fake)

    with db_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT code_hash FROM otp_codes WHERE phone = :phone"),
            {"phone": _PHONE},
        ).scalar_one()
    assert stored != code
    assert stored.startswith("$2")


@pytest.mark.asyncio
async def test_verify_wrong_code_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    _, code = await _register(http_client, sms_fake)
    wrong = "000000" if code != "000000" else "111111"

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": wrong, "purpose": "registration"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_verify_unknown_phone_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": "+2349099999999", "otp": "123456", "purpose": "registration"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_verify_already_used_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """Single-use enforcement. Exactly one OTP exists for this phone, so a
    second verify with the SAME correct code can only fail on used_at."""
    _, code = await _register(http_client, sms_fake)

    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT count(*) FROM otp_codes WHERE phone = :phone"),
            {"phone": _PHONE},
        ).scalar_one()
    assert rows == 1, "test is only meaningful with a single OTP row"

    first = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": code, "purpose": "registration"},
    )
    assert first.status_code == 200

    second = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": code, "purpose": "registration"},
    )
    assert second.status_code == 401
    assert_error_envelope(second.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_verify_expired_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    _, code = await _register(http_client, sms_fake)
    _expire_otp(db_engine)

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": code, "purpose": "registration"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "OTP_EXPIRED")
