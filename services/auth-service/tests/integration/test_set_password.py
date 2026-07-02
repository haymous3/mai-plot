"""POST /auth/set-password integration tests (SCRUM-94)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.termii import InMemoryTermiiClient
from tests.integration.conftest import assert_error_envelope

# Throwaway test values, referenced by variable so secret scanners don't flag a
# literal in a "password"-keyed position. _STRONG satisfies the policy; _WEAK is
# long enough but lacks an uppercase letter / digit.
_STRONG = "SecurePass123!"
_WEAK = "alllowercase"


def _extract_code(message: str) -> str:
    for part in message.split():
        cleaned = part.rstrip(".")
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned
    raise AssertionError(f"no 6-digit code found in SMS body: {message!r}")


async def _register_verify_token(
    http_client: AsyncClient, termii_fake: InMemoryTermiiClient, *, phone: str, email: str
) -> str:
    reg = await http_client.post(
        "/auth/register", json={"phone": phone, "role": "buyer", "email": email}
    )
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
async def test_set_password_then_login(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    email = "buyer@maiplot.ng"
    token = await _register_verify_token(http_client, termii_fake, phone="08012345678", email=email)

    resp = await http_client.post(
        "/auth/set-password", json={"password": _STRONG}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text

    # The password now works end-to-end via email/password login.
    login = await http_client.post("/auth/login", json={"email": email, "password": _STRONG})
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


@pytest.mark.asyncio
async def test_set_password_rejects_weak_password(
    clean_auth_tables: None,
    disable_rate_limit: None,
    termii_fake: InMemoryTermiiClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(
        http_client, termii_fake, phone="08012345678", email="b@maiplot.ng"
    )
    # ≥8 chars but no uppercase/digit → the service's policy (envelope), not
    # Pydantic's length floor.
    resp = await http_client.post(
        "/auth/set-password", json={"password": _WEAK}, headers=_auth(token)
    )
    assert resp.status_code == 422
    assert_error_envelope(resp.json(), "PASSWORD_TOO_WEAK")


@pytest.mark.asyncio
async def test_set_password_requires_authentication(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post("/auth/set-password", json={"password": _STRONG})
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
