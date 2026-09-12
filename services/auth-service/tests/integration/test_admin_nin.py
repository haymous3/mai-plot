"""Admin NIN console integration tests (SCRUM-224).

GET status (masked), POST reveal (audited, mandatory reason), PUT set/replace
(re-verified, deduped), DELETE clear (walks verified_status back), plus the
pre-migration "verified but not recoverable" row.

`register_and_verify` registers over the PHONE channel, so a fresh account
sits at `phone_verified` and a NIN lifts it to `id_verified`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.email_verification import InMemoryEmailClient
from app.adapters.nin import InMemoryNinVerifier, NinVerificationOutcome
from app.adapters.twilio import InMemoryTwilioClient
from tests.integration.conftest import (
    assert_error_envelope,
    extract_email_token,
    register_and_verify,
)
from tests.integration.test_admin_users import _auth, _staff_token

_NIN = "12345678901"
_OTHER_NIN = "98765432109"
_REASON = "Support ticket 4412: caller asked us to confirm identity."


async def _user_with_nin(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    *,
    phone: str = "08010000001",
    email: str = "u1@example.com",
    nin: str | None = _NIN,
) -> str:
    body = await register_and_verify(http_client, sms, phone=phone, role="buyer", email=email)
    user_id: str = body["user"]["id"]
    if nin:
        resp = await http_client.post(
            "/auth/verify/nin", json={"nin": nin}, headers=_auth(body["access_token"])
        )
        assert resp.status_code == 202, resp.text
    return user_id


def _pii_row(db_engine: Engine, user_id: str) -> Any:
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT p.nin_hash, p.nin_lookup, p.nin_encrypted, p.nin_last4, "
                "p.nin_verified_at, u.verified_status "
                "FROM user_pii p JOIN users u ON u.id = p.user_id WHERE p.user_id = :id"
            ),
            {"id": UUID(user_id)},
        ).first()


def _audit_rows(db_engine: Engine, action: str) -> list[Any]:
    with db_engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT actor_id, entity_id, old_value, new_value, ip_address "
                    "FROM audit_log WHERE action = :action ORDER BY created_at"
                ),
                {"action": action},
            )
        )


# --- registration now stores a recoverable copy ------------------------------


@pytest.mark.asyncio
async def test_self_verification_stores_encrypted_copy_and_last4(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake)

    row = _pii_row(db_engine, user_id)
    assert row is not None
    assert row.nin_encrypted is not None
    assert _NIN.encode() not in bytes(row.nin_encrypted)
    assert row.nin_last4 == "8901"
    assert row.nin_verified_at is not None
    # The pre-existing derivations are still written.
    assert row.nin_hash.startswith("$2") and len(row.nin_lookup) == 64


# --- status -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_is_masked_and_detail_still_carries_only_a_boolean(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake)
    _, admin = _staff_token(db_engine)

    resp = await http_client.get(f"/admin/users/{user_id}/nin", headers=_auth(admin))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "nin_verified": True,
        "nin_last4": "8901",
        "nin_verified_at": body["nin_verified_at"],
        "recoverable": True,
        # Null for a root account: it holds its own NIN (SCRUM-229).
        "held_by_user_id": None,
    }
    assert body["nin_verified_at"] is not None
    assert _NIN not in resp.text

    detail = await http_client.get(f"/admin/users/{user_id}", headers=_auth(admin))
    assert detail.json()["nin_verified"] is True
    assert "nin_last4" not in detail.json()
    assert _NIN not in detail.text


@pytest.mark.asyncio
async def test_status_without_a_nin(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake, nin=None)
    _, admin = _staff_token(db_engine)
    resp = await http_client.get(f"/admin/users/{user_id}/nin", headers=_auth(admin))
    assert resp.status_code == 200
    assert resp.json() == {
        "nin_verified": False,
        "nin_last4": None,
        "nin_verified_at": None,
        "recoverable": False,
        "held_by_user_id": None,
    }


# --- gate ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_nin_endpoint_requires_admin(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    body = await register_and_verify(
        http_client, sms_fake, phone="08010000001", role="buyer", email="u1@example.com"
    )
    user_id, own_token = body["user"]["id"], body["access_token"]
    _, legal = _staff_token(db_engine, role="legal_team")

    for token in (own_token, legal):
        h = _auth(token)
        assert (await http_client.get(f"/admin/users/{user_id}/nin", headers=h)).status_code == 403
        assert (
            await http_client.post(
                f"/admin/users/{user_id}/nin/reveal", json={"reason": _REASON}, headers=h
            )
        ).status_code == 403
        assert (
            await http_client.put(
                f"/admin/users/{user_id}/nin", json={"nin": _NIN, "reason": _REASON}, headers=h
            )
        ).status_code == 403
        assert (
            await http_client.request(
                "DELETE", f"/admin/users/{user_id}/nin", json={"reason": _REASON}, headers=h
            )
        ).status_code == 403
    assert (await http_client.get(f"/admin/users/{user_id}/nin")).status_code == 401


# --- reveal -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reveal_returns_the_nin_and_writes_an_audit_row(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake)
    admin_id, admin = _staff_token(db_engine)

    resp = await http_client.post(
        f"/admin/users/{user_id}/nin/reveal", json={"reason": _REASON}, headers=_auth(admin)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"nin": _NIN, "nin_last4": "8901"}

    rows = _audit_rows(db_engine, "user.nin_revealed_by_admin")
    assert len(rows) == 1
    assert rows[0].actor_id == admin_id
    assert rows[0].entity_id == UUID(user_id)
    assert rows[0].new_value == {"reason": _REASON, "nin_last4": "8901"}
    assert rows[0].ip_address is not None


@pytest.mark.asyncio
async def test_reveal_reason_is_mandatory(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake)
    _, admin = _staff_token(db_engine)

    for payload in ({}, {"reason": ""}, {"reason": "asked"}):
        resp = await http_client.post(
            f"/admin/users/{user_id}/nin/reveal", json=payload, headers=_auth(admin)
        )
        assert resp.status_code == 422, resp.text
        assert _NIN not in resp.text
    assert _audit_rows(db_engine, "user.nin_revealed_by_admin") == []


@pytest.mark.asyncio
async def test_reveal_404s_when_nothing_on_file(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake, nin=None)
    _, admin = _staff_token(db_engine)
    resp = await http_client.post(
        f"/admin/users/{user_id}/nin/reveal", json={"reason": _REASON}, headers=_auth(admin)
    )
    assert resp.status_code == 404
    assert_error_envelope(resp.json(), "NIN_NOT_ON_FILE")


@pytest.mark.asyncio
async def test_pre_migration_row_is_verified_but_not_recoverable(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """A NIN verified before migration 0016 has a hash and no ciphertext.
    Simulated by nulling the new columns on a freshly verified row."""
    user_id = await _user_with_nin(http_client, sms_fake)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE user_pii SET nin_encrypted = NULL, nin_last4 = NULL, "
                "nin_verified_at = NULL WHERE user_id = :id"
            ),
            {"id": UUID(user_id)},
        )
    _, admin = _staff_token(db_engine)

    status = await http_client.get(f"/admin/users/{user_id}/nin", headers=_auth(admin))
    assert status.json() == {
        "nin_verified": True,
        "nin_last4": None,
        "nin_verified_at": None,
        "recoverable": False,
        "held_by_user_id": None,
    }

    reveal = await http_client.post(
        f"/admin/users/{user_id}/nin/reveal", json={"reason": _REASON}, headers=_auth(admin)
    )
    assert reveal.status_code == 409
    assert_error_envelope(reveal.json(), "NIN_NOT_RECOVERABLE")

    # Replace is the remedy: same number, re-verified, now recoverable.
    replaced = await http_client.put(
        f"/admin/users/{user_id}/nin",
        json={"nin": _NIN, "reason": _REASON},
        headers=_auth(admin),
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["recoverable"] is True
    reveal = await http_client.post(
        f"/admin/users/{user_id}/nin/reveal", json={"reason": _REASON}, headers=_auth(admin)
    )
    assert reveal.status_code == 200 and reveal.json()["nin"] == _NIN


# --- set / replace --------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_creates_a_nin_for_a_user_without_one(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake, nin=None)
    admin_id, admin = _staff_token(db_engine)
    before = _pii_row(db_engine, user_id)
    assert before is not None and before.verified_status == "phone_verified"

    resp = await http_client.put(
        f"/admin/users/{user_id}/nin",
        json={"nin": _NIN, "reason": _REASON},
        headers=_auth(admin),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["nin_verified"] is True
    assert resp.json()["nin_last4"] == "8901"
    assert _NIN not in resp.text
    assert nin_fake.calls == 1  # re-verified with the registry
    row = _pii_row(db_engine, user_id)
    assert row is not None
    assert row.nin_encrypted is not None and row.verified_status == "id_verified"

    rows = _audit_rows(db_engine, "user.nin_set_by_admin")
    assert len(rows) == 1 and rows[0].actor_id == admin_id
    assert rows[0].old_value == {"nin_verified": False, "nin_last4": None}
    assert rows[0].new_value == {"nin_verified": True, "nin_last4": "8901", "reason": _REASON}


@pytest.mark.asyncio
async def test_set_replaces_an_existing_nin(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake)
    _, admin = _staff_token(db_engine)

    resp = await http_client.put(
        f"/admin/users/{user_id}/nin",
        json={"nin": _OTHER_NIN, "reason": _REASON},
        headers=_auth(admin),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["nin_last4"] == "2109"
    reveal = await http_client.post(
        f"/admin/users/{user_id}/nin/reveal", json={"reason": _REASON}, headers=_auth(admin)
    )
    assert reveal.json()["nin"] == _OTHER_NIN
    rows = _audit_rows(db_engine, "user.nin_set_by_admin")
    assert rows[0].old_value == {"nin_verified": True, "nin_last4": "8901"}


@pytest.mark.asyncio
async def test_set_refuses_a_nin_held_by_another_account(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await _user_with_nin(http_client, sms_fake, phone="08010000001", email="a@example.com")
    other = await _user_with_nin(
        http_client, sms_fake, phone="08010000002", email="b@example.com", nin=None
    )
    _, admin = _staff_token(db_engine)
    calls_before = nin_fake.calls

    resp = await http_client.put(
        f"/admin/users/{other}/nin", json={"nin": _NIN, "reason": _REASON}, headers=_auth(admin)
    )

    assert resp.status_code == 409
    assert_error_envelope(resp.json(), "NIN_BELONGS_TO_ANOTHER_ACCOUNT")
    assert nin_fake.calls == calls_before  # refused before a paid registry call
    row = _pii_row(db_engine, other)
    assert row is not None and row.nin_hash is None


@pytest.mark.asyncio
async def test_set_rejected_by_registry_stores_nothing(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake, nin=None)
    _, admin = _staff_token(db_engine)
    nin_fake.outcome = NinVerificationOutcome(status="failed", mismatches=("last_name",))

    resp = await http_client.put(
        f"/admin/users/{user_id}/nin", json={"nin": _NIN, "reason": _REASON}, headers=_auth(admin)
    )

    assert resp.status_code == 422
    assert resp.json()["error_code"] == "NIN_NOT_VERIFIED"
    assert resp.json()["details"] == {"status": "failed", "mismatches": ["last_name"]}
    assert _NIN not in resp.text
    row = _pii_row(db_engine, user_id)
    assert row is not None and row.nin_hash is None
    assert _audit_rows(db_engine, "user.nin_set_by_admin") == []


@pytest.mark.asyncio
async def test_set_validates_format_and_reason(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake, nin=None)
    _, admin = _staff_token(db_engine)

    letters = await http_client.put(
        f"/admin/users/{user_id}/nin",
        json={"nin": "1234567890a", "reason": _REASON},
        headers=_auth(admin),
    )
    assert letters.status_code == 422
    assert_error_envelope(letters.json(), "NIN_FORMAT_INVALID")
    assert "1234567890a" not in letters.text

    no_reason = await http_client.put(
        f"/admin/users/{user_id}/nin", json={"nin": _NIN}, headers=_auth(admin)
    )
    assert no_reason.status_code == 422
    assert nin_fake.calls == 0


# --- clear ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_removes_the_nin_and_walks_verified_status_back(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake)
    admin_id, admin = _staff_token(db_engine)
    before = _pii_row(db_engine, user_id)
    assert before is not None and before.verified_status == "id_verified"

    resp = await http_client.request(
        "DELETE", f"/admin/users/{user_id}/nin", json={"reason": _REASON}, headers=_auth(admin)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "nin_verified": False,
        "nin_last4": None,
        "nin_verified_at": None,
        "recoverable": False,
        "held_by_user_id": None,
    }
    row = _pii_row(db_engine, user_id)
    assert row is not None
    assert row.nin_hash is None and row.nin_lookup is None and row.nin_encrypted is None
    # Back to the rung below id_verified — the channel the account proved at
    # registration (the helper registers by phone) — not all the way down.
    assert row.verified_status == "phone_verified"
    rows = _audit_rows(db_engine, "user.nin_cleared_by_admin")
    assert len(rows) == 1 and rows[0].actor_id == admin_id
    assert rows[0].old_value == {"nin_verified": True, "nin_last4": "8901"}
    assert rows[0].new_value == {"nin_verified": False, "reason": _REASON}

    # The number is free again: another account may verify it.
    other = await _user_with_nin(
        http_client, sms_fake, phone="08010000002", email="b@example.com", nin=_NIN
    )
    assert other != user_id


@pytest.mark.asyncio
async def test_clear_keeps_id_verified_when_a_bvn_remains(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    user_id = await _user_with_nin(http_client, sms_fake)
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE user_pii SET bvn_hash = '$2b$fake', bvn_lookup = 'x' WHERE user_id = :id"),
            {"id": UUID(user_id)},
        )
    _, admin = _staff_token(db_engine)

    resp = await http_client.request(
        "DELETE", f"/admin/users/{user_id}/nin", json={"reason": _REASON}, headers=_auth(admin)
    )

    assert resp.status_code == 200, resp.text
    row = _pii_row(db_engine, user_id)
    assert row is not None and row.verified_status == "id_verified"


@pytest.mark.asyncio
async def test_clear_404s_when_nothing_on_file_and_409s_when_deleted(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    empty = await _user_with_nin(http_client, sms_fake, nin=None)
    deleted = await _user_with_nin(
        http_client, sms_fake, phone="08010000002", email="b@example.com"
    )
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET deleted_at = NOW() WHERE id = :id"), {"id": UUID(deleted)}
        )
    _, admin = _staff_token(db_engine)

    resp = await http_client.request(
        "DELETE", f"/admin/users/{empty}/nin", json={"reason": _REASON}, headers=_auth(admin)
    )
    assert resp.status_code == 404
    assert_error_envelope(resp.json(), "NIN_NOT_ON_FILE")

    resp = await http_client.request(
        "DELETE", f"/admin/users/{deleted}/nin", json={"reason": _REASON}, headers=_auth(admin)
    )
    assert resp.status_code == 409
    assert_error_envelope(resp.json(), "USER_DELETED")
    # ...but a reveal on the deleted account still works: a regulator request
    # does not stop at deletion.
    reveal = await http_client.post(
        f"/admin/users/{deleted}/nin/reveal", json={"reason": _REASON}, headers=_auth(admin)
    )
    assert reveal.status_code == 200 and reveal.json()["nin"] == _NIN


# ---------------------------------------------------------------------------
# Linked second accounts (SCRUM-229)
# ---------------------------------------------------------------------------


async def _linked_pair(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    email_fake: InMemoryEmailClient,
) -> tuple[str, str]:
    """A root holding the NIN, and a confirmed second account linked to it
    (SCRUM-225). Returns (root_id, linked_id)."""
    root_body = await register_and_verify(
        http_client, sms, phone="08010000001", role="buyer", email="root@example.com"
    )
    root_token = root_body["access_token"]
    await http_client.post(
        "/auth/profile",
        json={"full_name": "Adaeze Okonkwo", "address": "12 Marina, Lagos"},
        headers=_auth(root_token),
    )
    nin = await http_client.post("/auth/verify/nin", json={"nin": _NIN}, headers=_auth(root_token))
    assert nin.status_code == 202, nin.text

    email_fake.sent.clear()
    reg = await http_client.post(
        "/auth/register",
        json={
            "phone": "08087654321",
            "role": "realtor",
            "email": "second@example.com",
            "full_name": "Adaeze Okonkwo",
            "verification_channel": "email",
            "existing_account_nin": _NIN,
        },
    )
    assert reg.status_code == 201, reg.text
    token = extract_email_token(email_fake.sent[-1].verify_url)
    verify = await http_client.post(
        "/auth/verify/email", json={"token": token, "purpose": "registration"}
    )
    assert verify.status_code == 200, verify.text
    return root_body["user"]["id"], verify.json()["user"]["id"]


@pytest.mark.asyncio
async def test_admin_detail_of_a_linked_account_shows_verified_and_names_the_root(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """Before SCRUM-229 the detail derived nin_verified from the row's own hash
    and told an admin "not verified" about an account whose identity IS."""
    root_id, linked_id = await _linked_pair(http_client, sms_fake, email_verification_fake)
    _, admin = _staff_token(db_engine)

    resp = await http_client.get(f"/admin/users/{linked_id}", headers=_auth(admin))

    assert resp.status_code == 200, resp.text
    assert resp.json()["nin_verified"] is True
    assert resp.json()["linked_identity_user_id"] == root_id


@pytest.mark.asyncio
async def test_console_status_of_a_linked_account_reports_the_root(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    root_id, linked_id = await _linked_pair(http_client, sms_fake, email_verification_fake)
    _, admin = _staff_token(db_engine)

    resp = await http_client.get(f"/admin/users/{linked_id}/nin", headers=_auth(admin))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nin_verified"] is True
    assert body["nin_last4"] == "8901"
    assert body["held_by_user_id"] == root_id
    assert _NIN not in resp.text


@pytest.mark.asyncio
async def test_reveal_set_and_clear_on_a_linked_account_all_point_at_the_root(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    nin_fake: InMemoryNinVerifier,
    email_verification_fake: InMemoryEmailClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """Refused on purpose: the reveal audit belongs on the row that holds the
    number, and exactly one row owns a NIN. Each refusal names the root."""
    root_id, linked_id = await _linked_pair(http_client, sms_fake, email_verification_fake)
    _, admin = _staff_token(db_engine)
    base = f"/admin/users/{linked_id}/nin"

    reveal = await http_client.post(
        f"{base}/reveal", json={"reason": _REASON}, headers=_auth(admin)
    )
    set_ = await http_client.put(
        base, json={"nin": _OTHER_NIN, "reason": _REASON}, headers=_auth(admin)
    )
    clear = await http_client.request(
        "DELETE", base, json={"reason": _REASON}, headers=_auth(admin)
    )

    for resp in (reveal, set_, clear):
        assert resp.status_code == 409, resp.text
        assert_error_envelope(resp.json(), "NIN_HELD_BY_LINKED_ACCOUNT")
        assert resp.json()["details"]["held_by_user_id"] == root_id
    assert _NIN not in reveal.text

    # And nothing was written to the sibling, nor revealed anywhere.
    assert _pii_row(db_engine, linked_id).nin_hash is None
    assert _audit_rows(db_engine, "user.nin_revealed_by_admin") == []
