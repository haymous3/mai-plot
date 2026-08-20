"""POST /auth/logout integration tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, register_and_verify


def _auth(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    tokens = await register_and_verify(http_client, sms_fake)

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
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    tokens = await register_and_verify(http_client, sms_fake)

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
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    tokens = await register_and_verify(http_client, sms_fake)
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
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    tokens = await register_and_verify(http_client, sms_fake)
    headers = _auth(tokens["access_token"])
    body = {"refresh_token": tokens["refresh_token"]}

    first = await http_client.post("/auth/logout", json=body, headers=headers)
    assert first.status_code == 200
    # Logging out again with the same (now-revoked) token still succeeds.
    second = await http_client.post("/auth/logout", json=body, headers=headers)
    assert second.status_code == 200
