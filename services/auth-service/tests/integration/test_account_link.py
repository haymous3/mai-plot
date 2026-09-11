"""Registering a SECOND account against an existing NIN (SCRUM-225).

Exercises the whole path against a real database: the match, where the
confirmation email lands, the identity inherited on confirmation, and the
guards that stop this becoming a way to mint verified accounts.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.email_verification import InMemoryEmailClient
from app.adapters.nin import InMemoryNinVerifier
from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import (
    assert_error_envelope,
    extract_email_token,
    register_and_verify,
)

_NIN = "12345678901"
_NAME = "Adaeze Okonkwo"


async def _seed_root(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    *,
    role: str = "seller",
    email: str = "root@example.com",
    phone: str = "08012345678",
) -> tuple[str, str]:
    """A verified account holding the NIN. Returns (user_id, access_token)."""
    body = await register_and_verify(
        http_client,
        sms,
        phone=phone,
        role=role,
        email=email,
        seller_authority_type="owner" if role == "seller" else None,
    )
    token = body["access_token"]
    await http_client.post(
        "/auth/profile",
        json={"full_name": _NAME, "address": "12 Marina, Lagos"},
        headers={"Authorization": f"Bearer {token}"},
    )
    nin = await http_client.post(
        "/auth/verify/nin", json={"nin": _NIN}, headers={"Authorization": f"Bearer {token}"}
    )
    assert nin.status_code == 202, nin.text
    return body["user"]["id"], token


def _second_account_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phone": "08087654321",
        "role": "realtor",
        "email": "new-address@example.com",
        "full_name": _NAME,
        "verification_channel": "email",
        "existing_account_nin": _NIN,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_confirmation_goes_to_the_existing_account_not_the_new_address(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    """⚠️ THE security property of this feature. A NIN is not secret — it is on
    documents handed to banks and agents — so if this link went to the address
    typed into the form, knowing a NIN and a name would be enough to obtain an
    account the platform believes is a verified person."""
    await _seed_root(http_client, sms_fake)
    email_verification_fake.sent.clear()

    resp = await http_client.post("/auth/register", json=_second_account_payload())

    assert resp.status_code == 201, resp.text
    assert len(email_verification_fake.sent) == 1
    assert email_verification_fake.sent[-1].to == "root@example.com"
    assert email_verification_fake.sent[-1].to != "new-address@example.com"


@pytest.mark.asyncio
async def test_confirming_the_link_inherits_the_verified_identity(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    root_id, _ = await _seed_root(http_client, sms_fake)
    email_verification_fake.sent.clear()

    await http_client.post("/auth/register", json=_second_account_payload())
    token = extract_email_token(email_verification_fake.sent[-1].verify_url)

    verify = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )

    assert verify.status_code == 200, verify.text
    assert verify.json()["user"]["verified_status"] == "id_verified"

    new_id = verify.json()["user"]["id"]
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT linked_identity_user_id FROM users WHERE id = :id"), {"id": new_id}
        ).first()
        assert row is not None
        assert str(row.linked_identity_user_id) == root_id

        # ⚠️ The NIN stays on the ROOT. Writing it here too would collide with
        # idx_user_pii_nin_lookup, which is the guard this feature preserves.
        pii = conn.execute(
            text("SELECT nin_hash, nin_lookup FROM user_pii WHERE user_id = :id"), {"id": new_id}
        ).first()
        assert pii is not None
        assert pii.nin_hash is None
        assert pii.nin_lookup is None


@pytest.mark.asyncio
async def test_the_linked_account_is_not_asked_for_a_nin_again(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    """`nin_verified` has to resolve through the link, or onboarding sends them
    back through a step they have already passed."""
    await _seed_root(http_client, sms_fake)
    email_verification_fake.sent.clear()
    await http_client.post("/auth/register", json=_second_account_payload())
    token = extract_email_token(email_verification_fake.sent[-1].verify_url)
    verify = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )

    me = await http_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {verify.json()['access_token']}"}
    )

    assert me.status_code == 200, me.text
    assert me.json()["nin_verified"] is True


@pytest.mark.asyncio
async def test_a_wrong_name_falls_back_to_an_ordinary_signup(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """Same 201, and the email goes to the NEW address because nothing matched.
    The response is identical either way so this cannot enumerate NINs."""
    await _seed_root(http_client, sms_fake)
    email_verification_fake.sent.clear()

    resp = await http_client.post(
        "/auth/register", json=_second_account_payload(full_name="Somebody Else")
    )

    assert resp.status_code == 201, resp.text
    assert email_verification_fake.sent[-1].to == "new-address@example.com"
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT linked_identity_user_id FROM users WHERE email = :e"),
            {"e": "new-address@example.com"},
        ).first()
        assert row is not None
        assert row.linked_identity_user_id is None


@pytest.mark.asyncio
async def test_an_unknown_nin_falls_back_to_an_ordinary_signup(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    resp = await http_client.post(
        "/auth/register", json=_second_account_payload(existing_account_nin="99999999999")
    )

    assert resp.status_code == 201, resp.text
    assert email_verification_fake.sent[-1].to == "new-address@example.com"


@pytest.mark.asyncio
async def test_a_role_the_person_already_holds_is_refused(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    await _seed_root(http_client, sms_fake, role="seller")
    email_verification_fake.sent.clear()

    resp = await http_client.post(
        "/auth/register",
        json=_second_account_payload(role="seller", seller_authority_type="owner"),
    )

    assert resp.status_code == 409, resp.text
    assert_error_envelope(resp.json(), "ROLE_ALREADY_HELD")
    assert email_verification_fake.sent == []


@pytest.mark.asyncio
async def test_the_identity_root_cannot_be_deleted_while_linked(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
) -> None:
    """Deleting the root would leave the sibling id_verified against a NIN that
    can no longer be looked up."""
    _, root_token = await _seed_root(http_client, sms_fake)
    email_verification_fake.sent.clear()
    await http_client.post("/auth/register", json=_second_account_payload())
    token = extract_email_token(email_verification_fake.sent[-1].verify_url)
    await http_client.post("/auth/verify/email", json={"token": token, "purpose": "registration"})

    resp = await http_client.post(
        "/auth/account/delete", headers={"Authorization": f"Bearer {root_token}"}
    )

    assert resp.status_code == 409, resp.text
    assert_error_envelope(resp.json(), "ACCOUNT_IS_IDENTITY_ROOT")


@pytest.mark.asyncio
async def test_registering_without_the_field_is_completely_unchanged(
    clean_auth_tables: None,
    disable_rate_limit: None,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """The overwhelmingly common path: no claim of an existing account."""
    payload = _second_account_payload()
    payload.pop("existing_account_nin")

    resp = await http_client.post("/auth/register", json=payload)

    assert resp.status_code == 201, resp.text
    assert email_verification_fake.sent[-1].to == "new-address@example.com"
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT linked_identity_user_id FROM users WHERE email = :e"),
            {"e": "new-address@example.com"},
        ).first()
        assert row is not None
        assert row.linked_identity_user_id is None
