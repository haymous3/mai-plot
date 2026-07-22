"""POST /auth/profile integration tests (SCRUM-132)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.email_verification import InMemoryEmailClient
from tests.integration.conftest import assert_error_envelope, register_and_verify

# Throwaway password, referenced by variable so secret scanners don't flag a
# literal in a "password"-keyed position (mirrors test_set_password.py).
_STRONG = "SecurePass123!"


async def _register_verify_token(
    http_client: AsyncClient,
    email_fake: InMemoryEmailClient,
    *,
    phone: str,
    email: str | None = None,
) -> str:
    """Register + email-verify a buyer; return the access token. `email` is the
    REGISTRATION email (now required); when omitted a unique placeholder is
    derived from the phone so callers can register several accounts per test.
    The profile screen can then set/replace the email."""
    reg_email = email or f"user{phone[-4:]}@maiplot.ng"
    body = await register_and_verify(
        http_client, email_fake, phone=phone, role="buyer", email=reg_email
    )
    token: str = body["access_token"]
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_profile_persists_name_and_email(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(http_client, email_verification_fake, phone="08012345678")

    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Ada Obi", "email": "ada@maiplot.ng"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text

    # The email persisted end-to-end: set a password and log in with that email.
    pw_resp = await http_client.post(
        "/auth/set-password", json={"password": _STRONG}, headers=_auth(token)
    )
    assert pw_resp.status_code == 200
    login = await http_client.post(
        "/auth/login", json={"email": "ada@maiplot.ng", "password": _STRONG}
    )
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_profile_email_optional(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(http_client, email_verification_fake, phone="08012345678")
    resp = await http_client.post(
        "/auth/profile", json={"full_name": "Ada Obi"}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_profile_blank_name_rejected(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(http_client, email_verification_fake, phone="08012345678")
    resp = await http_client.post("/auth/profile", json={"full_name": "   "}, headers=_auth(token))
    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "FULL_NAME_REQUIRED")


@pytest.mark.asyncio
async def test_profile_email_collision_rejected(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # First account already owns the email (set at registration).
    await _register_verify_token(
        http_client, email_verification_fake, phone="08010000001", email="dup@maiplot.ng"
    )
    # Second account tries to claim the same email via the profile screen.
    token_b = await _register_verify_token(
        http_client, email_verification_fake, phone="08010000002"
    )
    resp = await http_client.post(
        "/auth/profile",
        json={"full_name": "Bola", "email": "dup@maiplot.ng"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 409
    assert_error_envelope(resp.json(), "EMAIL_ALREADY_IN_USE")


@pytest.mark.asyncio
async def test_profile_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/profile", json={"full_name": "Ada"})
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
