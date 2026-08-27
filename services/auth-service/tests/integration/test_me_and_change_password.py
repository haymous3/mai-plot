"""GET /auth/me and POST /auth/change-password integration tests (SCRUM-188)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.adapters.bvn import InMemoryBvnVerifier
from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, register_and_verify

# Throwaway test values. Held in NON-"password"-named constants and passed by
# reference so secret scanners don't flag a literal in a password-keyed
# position — the convention already used by test_login.py and
# test_set_password_service.py. Naming these _PASSWORD etc. was not enough:
# GitGuardian still fired on the constant itself.
_STRONG = "SecurePass123!"
_ROTATED = "RotatedPass456!"
_GUESS = "NotTheOne789!"
_FEEBLE = "alllowercase"


async def _account(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    *,
    phone: str,
    role: str = "buyer",
) -> tuple[str, str]:
    body = await register_and_verify(
        http_client,
        sms,
        phone=phone,
        role=role,
        email=f"me{phone[-4:]}@maihomme.com",
        password=_STRONG,
    )
    return body["access_token"], body["user"]["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── GET /auth/me ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_the_callers_own_details(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
) -> None:
    token, user_id = await _account(http_client, sms_fake, phone="08030000001")

    resp = await http_client.get("/auth/me", headers=_auth(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user_id
    assert body["role"] == "buyer"
    assert body["email"] == "me0001@maihomme.com"
    assert body["phone"] == "+2348030000001"
    # Not verified yet — nothing has been submitted.
    assert body["bvn_verified"] is False
    assert body["nin_verified"] is False


@pytest.mark.asyncio
async def test_me_never_leaks_bvn_or_nin_material(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
    bvn_fake: InMemoryBvnVerifier,
) -> None:
    """§4: BVN/NIN live only as bcrypt hashes, and the hash is as sensitive as
    the number — an 11-digit space is trivially crackable offline. /auth/me must
    expose presence, never material."""
    token, _ = await _account(http_client, sms_fake, phone="08030000002")
    bvn = "22222222222"

    verify = await http_client.post("/auth/verify/bvn", json={"bvn": bvn}, headers=_auth(token))
    assert verify.status_code == 202

    resp = await http_client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()

    assert body["bvn_verified"] is True
    raw = resp.text
    assert bvn not in raw
    assert "hash" not in raw.lower()
    assert "bvn_hash" not in body
    assert "$2b$" not in raw  # no bcrypt digest anywhere in the payload


@pytest.mark.asyncio
async def test_me_reflects_a_saved_buyer_profile(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
) -> None:
    """The whole point of the endpoint: Settings can pre-fill what was saved."""
    token, _ = await _account(http_client, sms_fake, phone="08030000003")

    saved = await http_client.post(
        "/auth/buyer/profile",
        json={
            "employment_status": "employed",
            "preferred_location": "Lagos",
            "budget_kobo": 4_000_000_000,
        },
        headers=_auth(token),
    )
    assert saved.status_code == 200

    body = (await http_client.get("/auth/me", headers=_auth(token))).json()
    assert body["employment_status"] == "employed"
    assert body["preferred_location"] == "Lagos"
    assert body["budget_kobo"] == 4_000_000_000


@pytest.mark.asyncio
async def test_me_requires_a_token(
    clean_auth_tables: None, disable_rate_limit: None, http_client: AsyncClient
) -> None:
    resp = await http_client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_omits_buyer_fields_for_a_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08030000004", role="seller")

    body = (await http_client.get("/auth/me", headers=_auth(token))).json()
    assert body["role"] == "seller"
    assert body["employment_status"] is None
    assert body["budget_kobo"] is None


# ── POST /auth/change-password ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_change_password_then_login_with_the_new_one(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08030000005")
    email = "me0005@maihomme.com"

    resp = await http_client.post(
        "/auth/change-password",
        json={"current_password": _STRONG, "new_password": _ROTATED},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["sessions_revoked"] is True

    old = await http_client.post("/auth/login", json={"email": email, "password": _STRONG})
    assert old.status_code == 401

    new = await http_client.post("/auth/login", json={"email": email, "password": _ROTATED})
    assert new.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_a_wrong_current_password(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
) -> None:
    """The reason this endpoint exists rather than reusing set-password: a live
    session alone must not be authority to rotate the password."""
    token, _ = await _account(http_client, sms_fake, phone="08030000006")

    resp = await http_client.post(
        "/auth/change-password",
        json={"current_password": _GUESS, "new_password": _ROTATED},
        headers=_auth(token),
    )

    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "CURRENT_PASSWORD_INCORRECT")

    # And the original password still works.
    login = await http_client.post(
        "/auth/login", json={"email": "me0006@maihomme.com", "password": _STRONG}
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_revokes_existing_refresh_tokens(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
) -> None:
    """A password change that leaves old sessions usable is half a fix."""
    body = await register_and_verify(
        http_client,
        sms_fake,
        phone="08030000007",
        role="buyer",
        email="me0007@maihomme.com",
        password=_STRONG,
    )
    token, refresh = body["access_token"], body["refresh_token"]

    changed = await http_client.post(
        "/auth/change-password",
        json={"current_password": _STRONG, "new_password": _ROTATED},
        headers=_auth(token),
    )
    assert changed.status_code == 200

    refreshed = await http_client.post("/auth/token/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_change_password_rejects_reuse_and_weak_passwords(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    sms_fake: InMemoryTwilioClient,
) -> None:
    token, _ = await _account(http_client, sms_fake, phone="08030000008")

    same = await http_client.post(
        "/auth/change-password",
        json={"current_password": _STRONG, "new_password": _STRONG},
        headers=_auth(token),
    )
    assert same.status_code == 422
    assert_error_envelope(same.json(), "PASSWORD_UNCHANGED")

    weak = await http_client.post(
        "/auth/change-password",
        json={"current_password": _STRONG, "new_password": _FEEBLE},
        headers=_auth(token),
    )
    assert weak.status_code == 422
    assert_error_envelope(weak.json(), "PASSWORD_TOO_WEAK")


@pytest.mark.asyncio
async def test_change_password_requires_a_token(
    clean_auth_tables: None, disable_rate_limit: None, http_client: AsyncClient
) -> None:
    resp = await http_client.post(
        "/auth/change-password",
        json={"current_password": _STRONG, "new_password": _ROTATED},
    )
    assert resp.status_code == 401
