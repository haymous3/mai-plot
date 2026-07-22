"""POST /auth/login integration tests (email + password)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.email_verification import InMemoryEmailClient
from tests.integration.conftest import assert_error_envelope

_EMAIL = "buyer@example.com"
_PASSWORD = "SecurePass123!"


async def _register_with_password(
    http_client: AsyncClient,
    phone: str = "08012345678",
    email: str = _EMAIL,
    password: str = _PASSWORD,
) -> None:
    reg = await http_client.post(
        "/auth/register",
        json={"phone": phone, "role": "buyer", "email": email, "password": password},
    )
    assert reg.status_code == 201, reg.text


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register_with_password(http_client)

    response = await http_client.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_expires_in"] == 900
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["role"] == "buyer"

    # The issued refresh token works on the rotation endpoint.
    refresh = await http_client.post(
        "/auth/token/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert refresh.status_code == 200


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register_with_password(http_client)
    response = await http_client.post(
        "/auth/login", json={"email": _EMAIL, "password": "WrongPassword1!"}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "INVALID_CREDENTIALS")


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": _PASSWORD}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "INVALID_CREDENTIALS")


@pytest.mark.asyncio
async def test_login_phone_only_user_has_no_password(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # Registered with an email but no password -> no credential row, so
    # login must fail with the same generic error (no enumeration).
    reg = await http_client.post(
        "/auth/register",
        json={"phone": "08012345678", "role": "buyer", "email": _EMAIL},
    )
    assert reg.status_code == 201

    response = await http_client.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert response.status_code == 401
    assert_error_envelope(response.json(), "INVALID_CREDENTIALS")
