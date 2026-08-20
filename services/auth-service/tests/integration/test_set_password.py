"""POST /auth/set-password integration tests (SCRUM-94)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, register_and_verify

# Throwaway test values, referenced by variable so secret scanners don't flag a
# literal in a "password"-keyed position. _STRONG satisfies the policy; _WEAK is
# long enough but lacks an uppercase letter / digit.
_STRONG = "SecurePass123!"
_WEAK = "alllowercase"


async def _register_verify_token(
    http_client: AsyncClient, sms: InMemoryTwilioClient, *, phone: str, email: str
) -> str:
    body = await register_and_verify(http_client, sms, phone=phone, role="buyer", email=email)
    token: str = body["access_token"]
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_set_password_then_login(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    email = "buyer@maiplot.ng"
    token = await _register_verify_token(http_client, sms_fake, phone="08012345678", email=email)

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
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    token = await _register_verify_token(
        http_client, sms_fake, phone="08012345678", email="b@maiplot.ng"
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
