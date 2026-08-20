"""POST /auth/token/refresh integration tests (rotation)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.adapters.twilio import InMemoryTwilioClient
from app.config import get_settings
from tests.integration.conftest import assert_error_envelope, register_and_verify


@pytest.mark.asyncio
async def test_refresh_rotates_and_issues_new_pair(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    tokens = await register_and_verify(http_client, sms_fake)
    old_refresh = tokens["refresh_token"]

    response = await http_client.post("/auth/token/refresh", json={"refresh_token": old_refresh})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_expires_in"] == 900
    assert body["access_token"]  # a fresh access token is returned
    # Rotation is the security-critical property: the refresh token is
    # always new. (The access token can be byte-identical when minted in
    # the same second — same iss/sub/role/iat/exp, no random claim — which
    # is harmless; only the refresh token carries a random jti.)
    assert body["refresh_token"] != old_refresh


@pytest.mark.asyncio
async def test_old_refresh_token_rejected_after_rotation(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    tokens = await register_and_verify(http_client, sms_fake)
    old_refresh = tokens["refresh_token"]

    first = await http_client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]

    # The consumed token is now revoked.
    replay = await http_client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401
    assert_error_envelope(replay.json(), "REFRESH_TOKEN_REVOKED")

    # The freshly minted token still works.
    third = await http_client.post("/auth/token/refresh", json={"refresh_token": new_refresh})
    assert third.status_code == 200


@pytest.mark.asyncio
async def test_refresh_unknown_token_returns_invalid(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/token/refresh", json={"refresh_token": "not-a-real-jwt"}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "REFRESH_TOKEN_INVALID")


@pytest.mark.asyncio
async def test_refresh_expired_token_returns_expired(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    # Forge a correctly-signed but expired refresh token with the app's
    # own secret/issuer. decode() rejects it on exp before any DB lookup.
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": "550e8400-e29b-41d4-a716-446655440000",
        "jti": "expired-token-jti",
        "iat": int((now - timedelta(days=8)).timestamp()),
        "exp": int((now - timedelta(days=1)).timestamp()),
        "type": "refresh",
    }
    expired = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    response = await http_client.post("/auth/token/refresh", json={"refresh_token": expired})
    assert response.status_code == 401
    assert_error_envelope(response.json(), "REFRESH_TOKEN_EXPIRED")


@pytest.mark.asyncio
async def test_access_token_cannot_be_used_as_refresh(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    tokens = await register_and_verify(http_client, sms_fake)
    # The access token is validly signed but has type=access; the refresh
    # path must reject it as invalid (type confusion guard).
    response = await http_client.post(
        "/auth/token/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "REFRESH_TOKEN_INVALID")
