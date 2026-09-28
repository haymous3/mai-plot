"""One sign-in for a person's buyer and seller accounts (SCRUM-236).

Against a real database: adding a role from inside an account, landing on the
buyer account at sign-in, switching, and the credential/profile/delete paths
that now have to act on the whole login rather than one row.
"""

from __future__ import annotations

from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.deals import InMemoryDealChecker
from app.adapters.email_verification import InMemoryEmailClient
from app.adapters.nin import InMemoryNinVerifier
from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import assert_error_envelope, register_and_verify

_EMAIL = "ada@example.com"
_PASSWORD = "SecurePass123!"
_ROTATED = "RotatedPass456!"
_NIN = "12345678901"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _verified(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    *,
    role: str = "buyer",
    verify_nin: bool = True,
) -> dict[str, Any]:
    """A signed-in account with a password and, by default, a verified NIN.
    Returns the session body (access_token, refresh_token, user)."""
    body = await register_and_verify(
        http_client,
        sms,
        role=role,
        email=_EMAIL,
        password=_PASSWORD,
        seller_authority_type="owner" if role == "seller" else None,
    )
    if verify_nin:
        nin = await http_client.post(
            "/auth/verify/nin", json={"nin": _NIN}, headers=_auth(body["access_token"])
        )
        assert nin.status_code == 202, nin.text
    return body


async def _add(http_client: AsyncClient, session: dict[str, Any], role: str) -> Any:
    return await http_client.post(
        "/auth/add-role",
        json={"role": role, "refresh_token": session["refresh_token"]},
        headers=_auth(session["access_token"]),
    )


async def _login(http_client: AsyncClient, email: str = _EMAIL, password: str = _PASSWORD) -> Any:
    return await http_client.post("/auth/login", json={"identifier": email, "password": password})


@pytest.mark.asyncio
async def test_adding_a_seller_account_skips_registration_and_shares_the_login(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _verified(http_client, sms_fake)

    resp = await _add(http_client, buyer, "seller")

    assert resp.status_code == 201, resp.text
    session = resp.json()
    assert session["user"]["role"] == "seller"
    assert session["user"]["verified_status"] == "id_verified"
    seller_id = session["user"]["id"]
    buyer_id = buyer["user"]["id"]

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT u.email, u.shares_login_with_user_id, u.linked_identity_user_id, "
                "u.seller_authority_type, p.first_name, p.last_name, p.nin_hash "
                "FROM users u JOIN user_pii p ON p.user_id = u.id WHERE u.id = :id"
            ),
            {"id": seller_id},
        ).first()
    assert row is not None
    assert row.email == _EMAIL
    assert str(row.shares_login_with_user_id) == buyer_id
    assert str(row.linked_identity_user_id) == buyer_id
    assert (row.first_name, row.last_name) == ("Ada", "Obi")
    # Declared in seller onboarding, never inherited.
    assert row.seller_authority_type is None
    # The NIN stays on the root; the unique index is untouched.
    assert row.nin_hash is None

    me = await http_client.get("/auth/me", headers=_auth(session["access_token"]))
    assert me.status_code == 200, me.text
    assert me.json()["nin_verified"] is True
    assert me.json()["available_roles"] == ["buyer", "seller"]

    [receipt] = email_verification_fake.sent_role_added
    assert (receipt.to, receipt.role) == (_EMAIL, "seller")


@pytest.mark.asyncio
async def test_sign_in_lands_on_the_buyer_account_and_switches_to_the_seller(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    # Seller FIRST, so the login owner is the seller row and landing on the
    # buyer is a real choice, not an accident of which row holds the password.
    seller = await _verified(http_client, sms_fake, role="seller")
    added = await _add(http_client, seller, "buyer")
    assert added.status_code == 201, added.text

    login = await _login(http_client)
    assert login.status_code == 200, login.text
    landed = login.json()
    assert landed["user"]["role"] == "buyer"

    switch = await http_client.post(
        "/auth/switch-role",
        json={"role": "seller", "refresh_token": landed["refresh_token"]},
        headers=_auth(landed["access_token"]),
    )
    assert switch.status_code == 200, switch.text
    assert switch.json()["user"]["id"] == seller["user"]["id"]

    # The session left behind is retired, not merely abandoned.
    replay = await http_client.post(
        "/auth/token/refresh", json={"refresh_token": landed["refresh_token"]}
    )
    assert replay.status_code == 401
    assert_error_envelope(replay.json(), "REFRESH_TOKEN_REVOKED")

    # And back again.
    back = await http_client.post(
        "/auth/switch-role", json={"role": "buyer"}, headers=_auth(switch.json()["access_token"])
    )
    assert back.status_code == 200, back.text
    assert back.json()["user"]["role"] == "buyer"


@pytest.mark.asyncio
async def test_the_token_names_the_other_account_for_the_own_listing_guard(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    buyer = await _verified(http_client, sms_fake)
    seller = (await _add(http_client, buyer, "seller")).json()

    login = await _login(http_client)
    claims = jwt.decode(login.json()["access_token"], options={"verify_signature": False})

    assert claims["sub"] == buyer["user"]["id"]
    assert claims["linked_user_ids"] == [seller["user"]["id"]]


@pytest.mark.asyncio
async def test_adding_a_role_needs_a_verified_nin(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _verified(http_client, sms_fake, verify_nin=False)

    resp = await _add(http_client, buyer, "seller")

    assert resp.status_code == 409
    assert_error_envelope(resp.json(), "NIN_VERIFICATION_REQUIRED")
    with db_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM users")).scalar_one()
    assert count == 1
    assert email_verification_fake.sent_role_added == []


@pytest.mark.asyncio
async def test_a_role_can_only_be_added_once(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    buyer = await _verified(http_client, sms_fake)
    assert (await _add(http_client, buyer, "seller")).status_code == 201

    again = await http_client.post(
        "/auth/add-role", json={"role": "seller"}, headers=_auth(buyer["access_token"])
    )

    assert again.status_code == 409
    assert_error_envelope(again.json(), "ROLE_ALREADY_HELD")


@pytest.mark.asyncio
async def test_switching_to_a_role_you_do_not_have_is_404(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
) -> None:
    buyer = await _verified(http_client, sms_fake)

    resp = await http_client.post(
        "/auth/switch-role", json={"role": "seller"}, headers=_auth(buyer["access_token"])
    )

    assert resp.status_code == 404
    assert_error_envelope(resp.json(), "ROLE_NOT_HELD")


@pytest.mark.asyncio
async def test_realtors_cannot_switch(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
) -> None:
    realtor = await register_and_verify(
        http_client, sms_fake, role="realtor", email="agent@example.com", password=_PASSWORD
    )

    resp = await http_client.post(
        "/auth/add-role", json={"role": "seller"}, headers=_auth(realtor["access_token"])
    )

    assert resp.status_code == 403
    assert_error_envelope(resp.json(), "ROLE_NOT_SWITCHABLE")


@pytest.mark.asyncio
async def test_the_shared_address_still_cannot_register_a_new_account(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    """The email index now excludes sharers; registration must still refuse."""
    buyer = await _verified(http_client, sms_fake)
    await _add(http_client, buyer, "seller")

    resp = await http_client.post(
        "/auth/register",
        json={
            "phone": "08099999999",
            "role": "realtor",
            "email": _EMAIL,
            "first_name": "Someone",
            "last_name": "Else",
            "verification_channel": "email",
        },
    )

    assert resp.status_code == 400
    assert_error_envelope(resp.json(), "EMAIL_ALREADY_REGISTERED")


@pytest.mark.asyncio
async def test_email_and_password_changed_from_the_seller_account_apply_to_the_login(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _verified(http_client, sms_fake)
    seller = (await _add(http_client, buyer, "seller")).json()

    profile = await http_client.post(
        "/auth/profile",
        json={"email": "ada.new@example.com"},
        headers=_auth(seller["access_token"]),
    )
    assert profile.status_code == 200, profile.text
    with db_engine.connect() as conn:
        emails = {
            r.email for r in conn.execute(text("SELECT email FROM users WHERE deleted_at IS NULL"))
        }
    assert emails == {"ada.new@example.com"}

    change = await http_client.post(
        "/auth/change-password",
        json={"current_password": _PASSWORD, "new_password": _ROTATED},
        headers=_auth(seller["access_token"]),
    )
    assert change.status_code == 200, change.text

    assert (await _login(http_client, "ada.new@example.com", _PASSWORD)).status_code == 401
    relogin = await _login(http_client, "ada.new@example.com", _ROTATED)
    assert relogin.status_code == 200, relogin.text
    assert relogin.json()["user"]["role"] == "buyer"

    # Both accounts' sessions went with the old password.
    stale = await http_client.post(
        "/auth/token/refresh", json={"refresh_token": seller["refresh_token"]}
    )
    assert stale.status_code == 401


@pytest.mark.asyncio
async def test_the_login_owner_is_deleted_after_the_account_sharing_it(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    deals_fake: InMemoryDealChecker,
    http_client: AsyncClient,
) -> None:
    buyer = await _verified(http_client, sms_fake)
    seller = (await _add(http_client, buyer, "seller")).json()

    first = await http_client.post("/auth/account/delete", headers=_auth(buyer["access_token"]))
    assert first.status_code == 409
    assert_error_envelope(first.json(), "ACCOUNT_HAS_OTHER_ROLES")

    assert (
        await http_client.post("/auth/account/delete", headers=_auth(seller["access_token"]))
    ).status_code == 200
    assert (
        await http_client.post("/auth/account/delete", headers=_auth(buyer["access_token"]))
    ).status_code == 200
