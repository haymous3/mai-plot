"""POST /auth/otp/verify integration tests."""

from __future__ import annotations

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.termii import InMemoryTermiiClient
from app.config import get_settings
from tests.integration.conftest import assert_error_envelope


async def _register(http_client: AsyncClient, phone: str = "08012345678") -> dict[str, object]:
    response = await http_client.post("/auth/register", json={"phone": phone, "role": "buyer"})
    assert response.status_code == 201, response.text
    # httpx's .json() is typed Any; pin it to the declared return type so
    # mypy's no-any-return (run as `mypy app tests` in CI) stays happy.
    body: dict[str, object] = response.json()
    return body


def _extract_code(message: str) -> str:
    for part in message.split():
        cleaned = part.rstrip(".")
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
    raise AssertionError(f"no 6-digit code found in SMS body: {message!r}")


@pytest.mark.asyncio
async def test_verify_happy_path_issues_tokens(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    register_body = await _register(http_client)
    code = _extract_code(termii_fake.sent[0].message)

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": "+2348012345678", "otp": code, "purpose": "registration"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_expires_in"] == 15 * 60
    assert body["user"]["id"] == register_body["user_id"]
    assert body["user"]["role"] == "buyer"
    assert body["user"]["verified_status"] == "phone_verified"

    # Access token has the Kong-expected shape.
    settings = get_settings()
    payload = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert payload["iss"] == settings.jwt_issuer
    assert payload["sub"] == register_body["user_id"]
    assert payload["role"] == "buyer"

    # OTP marked used; refresh token row persisted; user verified_status updated.
    with db_engine.connect() as conn:
        used = conn.execute(
            text(
                "SELECT count(*) FROM otp_codes "
                "WHERE phone = '+2348012345678' AND used_at IS NOT NULL"
            )
        ).scalar_one()
        assert used == 1

        rt_count = conn.execute(
            text("SELECT count(*) FROM refresh_tokens WHERE user_id = :id"),
            {"id": register_body["user_id"]},
        ).scalar_one()
        assert rt_count == 1

        verified = conn.execute(
            text("SELECT verified_status FROM users WHERE id = :id"),
            {"id": register_body["user_id"]},
        ).scalar_one()
        assert verified == "phone_verified"


@pytest.mark.asyncio
async def test_verify_wrong_code_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": "+2348012345678", "otp": "000000", "purpose": "registration"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_verify_unknown_phone_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
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
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)
    code = _extract_code(termii_fake.sent[0].message)

    first = await http_client.post(
        "/auth/otp/verify",
        json={"phone": "+2348012345678", "otp": code, "purpose": "registration"},
    )
    assert first.status_code == 200

    second = await http_client.post(
        "/auth/otp/verify",
        json={"phone": "+2348012345678", "otp": code, "purpose": "registration"},
    )
    assert second.status_code == 401
    assert_error_envelope(second.json(), "OTP_INVALID")


@pytest.mark.asyncio
async def test_verify_expired_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await _register(http_client)
    code = _extract_code(termii_fake.sent[0].message)

    # Force expiry by reaching into the row directly. Simpler than
    # freezegun across async + asyncpg + sync test session.
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE otp_codes SET expires_at = NOW() - INTERVAL '1 minute'"))

    response = await http_client.post(
        "/auth/otp/verify",
        json={"phone": "+2348012345678", "otp": code, "purpose": "registration"},
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "OTP_EXPIRED")
