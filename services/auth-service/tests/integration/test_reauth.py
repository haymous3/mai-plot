"""POST /auth/reauth — re-enter the password before a sensitive change (SCRUM-223)."""

from __future__ import annotations

from typing import Any

import jwt
import pytest
from httpx import AsyncClient

from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, register_and_verify

_PASSWORD = "SecurePass123!"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seller(http_client: AsyncClient, sms: InMemoryTwilioClient) -> dict[str, Any]:
    return await register_and_verify(
        http_client,
        sms,
        role="seller",
        email="seller@example.com",
        password=_PASSWORD,
        seller_authority_type="owner",
    )


@pytest.mark.asyncio
async def test_the_right_password_returns_a_reauth_token_for_the_caller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    session = await _seller(http_client, sms_fake)

    resp = await http_client.post(
        "/auth/reauth", json={"password": _PASSWORD}, headers=_auth(session["access_token"])
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expires_in"] == 300
    claims = jwt.decode(body["reauth_token"], options={"verify_signature": False})
    assert claims["type"] == "reauth"
    assert claims["sub"] == session["user"]["id"]


@pytest.mark.asyncio
async def test_a_wrong_password_is_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    session = await _seller(http_client, sms_fake)

    resp = await http_client.post(
        "/auth/reauth", json={"password": "WrongPass123!"}, headers=_auth(session["access_token"])
    )

    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "PASSWORD_INCORRECT")


@pytest.mark.asyncio
async def test_it_needs_a_session(http_client: AsyncClient) -> None:
    resp = await http_client.post("/auth/reauth", json={"password": _PASSWORD})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_repeated_guesses_are_rate_limited(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    """Route-level: the 11th attempt in the window is 429. The limiter is the
    conftest's in-memory stand-in with the production cap (10/hour)."""
    session = await _seller(http_client, sms_fake)
    headers = _auth(session["access_token"])

    statuses = [
        (
            await http_client.post(
                "/auth/reauth", json={"password": "WrongPass123!"}, headers=headers
            )
        ).status_code
        for _ in range(11)
    ]

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
