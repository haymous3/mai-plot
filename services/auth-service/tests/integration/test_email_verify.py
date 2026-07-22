"""POST /auth/verify/email integration tests (SCRUM-152)."""

from __future__ import annotations

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.email_verification import InMemoryEmailClient
from app.config import get_settings
from tests.integration.conftest import assert_error_envelope, extract_email_token

_EMAIL = "buyer@example.com"


async def _register(
    http_client: AsyncClient, email: str = _EMAIL, phone: str = "08012345678"
) -> dict[str, object]:
    response = await http_client.post(
        "/auth/register", json={"phone": phone, "role": "buyer", "email": email}
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


@pytest.mark.asyncio
async def test_verify_happy_path_issues_tokens(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    register_body = await _register(http_client)
    token = extract_email_token(email_verification_fake.sent[0].verify_url)

    response = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_expires_in"] == 15 * 60
    assert body["user"]["id"] == register_body["user_id"]
    assert body["user"]["role"] == "buyer"
    assert body["user"]["verified_status"] == "email_verified"

    # Access token has the Kong-expected shape.
    settings = get_settings()
    payload = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert payload["iss"] == settings.jwt_issuer
    assert payload["sub"] == register_body["user_id"]
    assert payload["role"] == "buyer"

    # Token marked used; refresh token row persisted; user status advanced.
    with db_engine.connect() as conn:
        used = conn.execute(
            text(
                "SELECT count(*) FROM email_verification_tokens "
                "WHERE user_id = :id AND used_at IS NOT NULL"
            ),
            {"id": register_body["user_id"]},
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
        assert verified == "email_verified"


@pytest.mark.asyncio
async def test_verify_unknown_token_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    response = await http_client.post(
        "/auth/verify/email", json={"token": "no-such-token", "purpose": "registration"}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "EMAIL_TOKEN_INVALID")


@pytest.mark.asyncio
async def test_verify_already_used_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _register(http_client)
    token = extract_email_token(email_verification_fake.sent[0].verify_url)

    first = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )
    assert first.status_code == 200

    second = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )
    assert second.status_code == 401
    assert_error_envelope(second.json(), "EMAIL_TOKEN_INVALID")


@pytest.mark.asyncio
async def test_verify_wrong_purpose_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # A token minted for 'registration' must not satisfy a 'reset' verify.
    await _register(http_client)
    token = extract_email_token(email_verification_fake.sent[0].verify_url)

    response = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "reset"}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "EMAIL_TOKEN_INVALID")


@pytest.mark.asyncio
async def test_verify_expired_returns_401(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await _register(http_client)
    token = extract_email_token(email_verification_fake.sent[0].verify_url)

    # Force expiry by reaching into the row directly (simpler than freezegun
    # across async + asyncpg + the sync test session).
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE email_verification_tokens SET expires_at = NOW() - INTERVAL '1 minute'")
        )

    response = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )
    assert response.status_code == 401
    assert_error_envelope(response.json(), "EMAIL_TOKEN_EXPIRED")
