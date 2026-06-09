"""POST /auth/logout integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope


def _extract_code(message: str) -> str:
    for part in message.split():
        cleaned = part.rstrip(".")
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
    raise AssertionError(f"no 6-digit code found in SMS body: {message!r}")


async def _register_and_verify(
    http_client: AsyncClient, termii_fake: InMemoryTermiiClient, phone: str = "08012345678"
) -> dict[str, object]:
    reg = await http_client.post("/auth/register", json={"phone": phone, "role": "buyer"})
    assert reg.status_code == 201, reg.text
    code = _extract_code(termii_fake.sent[-1].message)
    verify = await http_client.post(
        "/auth/otp/verify",
        json={"phone": phone, "otp": code, "purpose": "registration"},
    )
    assert verify.status_code == 200, verify.text
    body: dict[str, object] = verify.json()
    return body


def _auth(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    tokens = await _register_and_verify(http_client, termii_fake)

    response = await http_client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=_auth(tokens["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Logged out successfully"

    # The revoked refresh token can no longer be used.
    refresh = await http_client.post(
        "/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh.status_code == 401
    assert_error_envelope(refresh.json(), "REFRESH_TOKEN_REVOKED")


@pytest.mark.asyncio
async def test_logout_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    tokens = await _register_and_verify(http_client, termii_fake)

    # No Authorization header -> 401, and the token stays usable.
    response = await http_client.post(
        "/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "UNAUTHORIZED")

    refresh = await http_client.post(
        "/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh.status_code == 200


@pytest.mark.asyncio
async def test_logout_rejects_garbage_access_token(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    tokens = await _register_and_verify(http_client, termii_fake)
    response = await http_client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=_auth("garbage.token.value"),
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "TOKEN_INVALID")


@pytest.mark.asyncio
async def test_logout_is_idempotent(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    tokens = await _register_and_verify(http_client, termii_fake)
    headers = _auth(tokens["access_token"])
    body = {"refresh_token": tokens["refresh_token"]}

    first = await http_client.post("/auth/logout", json=body, headers=headers)
    assert first.status_code == 200
    # Logging out again with the same (now-revoked) token still succeeds.
    second = await http_client.post("/auth/logout", json=body, headers=headers)
    assert second.status_code == 200
