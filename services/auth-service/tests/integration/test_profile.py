"""POST /auth/profile integration tests (SCRUM-132)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope

# Throwaway password, referenced by variable so secret scanners don't flag a
# literal in a "password"-keyed position (mirrors test_set_password.py).
_STRONG = "SecurePass123!"


def _extract_code(message: str) -> str:
    for part in message.split():
        cleaned = part.rstrip(".")
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
    raise AssertionError(f"no 6-digit code found in SMS body: {message!r}")


async def _register_verify_token(
    http_client: AsyncClient,
    termii_fake: InMemoryTermiiClient,
    *,
    phone: str,
    email: str | None = None,
) -> str:
    payload: dict[str, str] = {"phone": phone, "role": "buyer"}
    if email is not None:
        payload["email"] = email
    reg = await http_client.post("/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    code = _extract_code(termii_fake.sent[-1].message)
    verify = await http_client.post(
        "/auth/otp/verify", json={"phone": phone, "otp": code, "purpose": "registration"}
    )
    assert verify.status_code == 200, verify.text
    token: str = verify.json()["access_token"]
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_profile_persists_name_and_email(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(http_client, termii_fake, phone="08012345678")

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
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(http_client, termii_fake, phone="08012345678")
    resp = await http_client.post(
        "/auth/profile", json={"full_name": "Ada Obi"}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_profile_blank_name_rejected(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(http_client, termii_fake, phone="08012345678")
    resp = await http_client.post("/auth/profile", json={"full_name": "   "}, headers=_auth(token))
    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "FULL_NAME_REQUIRED")


@pytest.mark.asyncio
async def test_profile_email_collision_rejected(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    # First account already owns the email (set at registration).
    await _register_verify_token(
        http_client, termii_fake, phone="08010000001", email="dup@maiplot.ng"
    )
    # Second account tries to claim the same email via the profile screen.
    token_b = await _register_verify_token(http_client, termii_fake, phone="08010000002")
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
