"""POST /auth/otp/verify integration tests.

The phone-OTP verify path stays live (SCRUM-152 only swapped the *delivery*
channel at registration to email). Registration no longer emits an OTP, so
these tests seed an otp_codes row directly and register with an email.
"""

from __future__ import annotations

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.email_verification import InMemoryEmailClient
from app.config import get_settings
from app.services.otp import hash_code
from tests.integration.conftest import assert_error_envelope

_PHONE = "+2348012345678"
_CODE = "123456"


async def _register(
    http_client: AsyncClient, email: str = "buyer@example.com", phone: str = "08012345678"
) -> str:
    """Register a user (email flow) and return its id."""
    response = await http_client.post(
        "/auth/register", json={"phone": phone, "role": "buyer", "email": email}
    )
    assert response.status_code == 201, response.text
    user_id: str = response.json()["user_id"]
    return user_id


def _seed_otp(
    db_engine: Engine, *, phone: str = _PHONE, code: str = _CODE, expired: bool = False
) -> None:
    """Insert a live (or expired) registration OTP for `phone`."""
    interval = "- INTERVAL '1 minute'" if expired else "+ INTERVAL '5 minutes'"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO otp_codes (phone, code_hash, purpose, expires_at) "
                f"VALUES (:phone, :code_hash, 'registration', NOW() {interval})"
            ),
            {"phone": phone, "code_hash": hash_code(code)},
        )


@pytest.mark.asyncio
async def test_verify_happy_path_issues_tokens(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _register(http_client)
    _seed_otp(db_engine)

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": _CODE, "purpose": "registration"},
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
            text(f"SELECT count(*) FROM otp_codes WHERE phone = '{_PHONE}' AND used_at IS NOT NULL")
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
async def test_verify_wrong_code_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await _register(http_client)
    _seed_otp(db_engine)

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": "000000", "purpose": "registration"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_verify_unknown_phone_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
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
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await _register(http_client)
    _seed_otp(db_engine)

    first = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": _CODE, "purpose": "registration"},
    )
    assert first.status_code == 200

    second = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": _CODE, "purpose": "registration"},
    )
    assert second.status_code == 401
    assert_error_envelope(second.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_verify_expired_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await _register(http_client)
    _seed_otp(db_engine, expired=True)

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": _PHONE, "otp": _CODE, "purpose": "registration"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "OTP_EXPIRED")
