"""Admin user console integration tests (SCRUM-209).

Covers the list + search + role filter, the audited detail read, the narrow edit
surface, suspend/reactivate, and the soft delete with its fail-closed guard.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.deals import InMemoryDealChecker
from app.adapters.twilio import InMemoryTwilioClient
from app.config import get_settings
from app.services.jwt_service import JwtService
from tests.integration.conftest import assert_error_envelope, register_and_verify

_PASSWORD = "SecurePass123!"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _staff_token(db_engine: Engine, *, role: str = "admin") -> tuple[UUID, str]:
    """Seed a staff account and mint a matching access token — admin and
    legal_team users are provisioned out of band, never via /auth/register."""
    settings = get_settings()
    user_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, role, verified_status, is_active) "
                "VALUES (:id, :role, 'id_verified', TRUE)"
            ),
            {"id": user_id, "role": role},
        )
    jwt = JwtService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_expire_minutes=settings.jwt_access_expire_minutes,
        refresh_expire_days=settings.jwt_refresh_expire_days,
    )
    return user_id, jwt.issue_pair(user_id=user_id, role=role).access_token


async def _register(
    http_client: AsyncClient,
    sms: InMemoryTwilioClient,
    *,
    role: str,
    phone: str,
    email: str,
    full_name: str | None = None,
) -> str:
    body = await register_and_verify(
        http_client, sms, phone=phone, role=role, email=email, password=_PASSWORD
    )
    user_id: str = body["user"]["id"]
    if full_name:
        # register_and_verify stores full_name or "", so set it explicitly when a
        # test needs to search by name.
        await http_client.post(
            "/auth/profile",
            json={"full_name": full_name},
            headers=_auth(body["access_token"]),
        )
    return user_id


@pytest.mark.asyncio
async def test_list_shows_every_role_and_the_realtor_number(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08010000001", email="b1@example.com"
    )
    realtor = await _register(
        http_client, sms_fake, role="realtor", phone="08010000002", email="r1@example.com"
    )
    _, admin = _staff_token(db_engine)
    issued = await http_client.post(
        f"/internal/realtors/{realtor}/registration-number", headers=_auth(admin)
    )
    number = issued.json()["registration_number"]

    resp = await http_client.get("/admin/users", headers=_auth(admin))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[buyer]["role"] == "buyer"
    assert by_id[buyer]["registration_number"] is None
    # A realtor's sign-in number rides along so a support call that opens with
    # "my number is MH-R-…" can be matched to an account.
    assert by_id[realtor]["registration_number"] == number
    assert body["pagination"]["total"] >= 3  # both users + the seeded admin
    # ⚠️ The LIST must not carry verification hashes/booleans — it is a browse
    # surface over the whole user base.
    assert "bvn_verified" not in by_id[buyer]


@pytest.mark.asyncio
async def test_role_filter_and_search(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    await _register(
        http_client,
        sms_fake,
        role="seller",
        phone="08020000001",
        email="ngozi@example.com",
        full_name="Ngozi Eze",
    )
    await _register(
        http_client, sms_fake, role="buyer", phone="08020000002", email="chidi@example.com"
    )
    _, admin = _staff_token(db_engine)

    sellers = await http_client.get("/admin/users?role=seller", headers=_auth(admin))
    assert [i["email"] for i in sellers.json()["items"]] == ["ngozi@example.com"]

    by_name = await http_client.get("/admin/users?search=ngozi", headers=_auth(admin))
    assert [i["email"] for i in by_name.json()["items"]] == ["ngozi@example.com"]

    by_email = await http_client.get("/admin/users?search=chidi@", headers=_auth(admin))
    assert [i["email"] for i in by_email.json()["items"]] == ["chidi@example.com"]

    # Typed as the caller reads it out ("0802…") while the column holds +234802…
    as_typed = await http_client.get("/admin/users?search=08020000001", headers=_auth(admin))
    assert [i["email"] for i in as_typed.json()["items"]] == ["ngozi@example.com"]


@pytest.mark.asyncio
async def test_list_requires_admin_and_rejects_legal_team(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """legal_team reviews powers of attorney; the user console is admin's. Same
    split as the realtor and document queues in their own services."""
    assert (await http_client.get("/admin/users")).status_code == 401
    _, legal = _staff_token(db_engine, role="legal_team")
    forbidden = await http_client.get("/admin/users", headers=_auth(legal))
    assert forbidden.status_code == 403
    assert_error_envelope(forbidden.json(), "ADMIN_FORBIDDEN")


@pytest.mark.asyncio
async def test_detail_is_audited_and_hides_identifier_values(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08030000001", email="d1@example.com"
    )
    admin_id, admin = _staff_token(db_engine)

    resp = await http_client.get(f"/admin/users/{buyer}", headers=_auth(admin))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bvn_verified"] is False and body["nin_verified"] is False
    # Booleans only — the hash is as sensitive as the number itself (§4).
    assert "bvn_hash" not in body and "nin_hash" not in body

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT actor_id FROM audit_log WHERE action = 'user.viewed_by_admin' "
                "AND entity_id = :id"
            ),
            {"id": buyer},
        ).one()
    assert row.actor_id == admin_id


@pytest.mark.asyncio
async def test_update_edits_profile_and_records_before_after(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _register(
        http_client,
        sms_fake,
        role="buyer",
        phone="08040000001",
        email="e1@example.com",
        full_name="Old Name",
    )
    _, admin = _staff_token(db_engine)

    resp = await http_client.patch(
        f"/admin/users/{buyer}",
        json={"full_name": "New Name", "location": "Lagos"},
        headers=_auth(admin),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "New Name"
    assert resp.json()["location"] == "Lagos"

    with db_engine.connect() as conn:
        old, new = conn.execute(
            text(
                "SELECT old_value, new_value FROM audit_log "
                "WHERE action = 'user.updated_by_admin' AND entity_id = :id"
            ),
            {"id": buyer},
        ).one()
    # "An admin changed this" is useless without what it used to say.
    assert old["full_name"] == "Old Name"
    assert new["full_name"] == "New Name"


@pytest.mark.asyncio
async def test_update_ignores_role_and_email(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """The escalation guard. A request naming role or email is not rewarded with a
    422 — the fields are simply not part of the contract, so a stale form cannot
    half-work — but they must NOT be applied."""
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08050000001", email="f1@example.com"
    )
    _, admin = _staff_token(db_engine)

    resp = await http_client.patch(
        f"/admin/users/{buyer}",
        json={"full_name": "Still A Buyer", "role": "admin", "email": "hijack@example.com"},
        headers=_auth(admin),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "buyer"
    assert body["email"] == "f1@example.com"


@pytest.mark.asyncio
async def test_update_with_no_editable_field_is_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08060000001", email="g1@example.com"
    )
    _, admin = _staff_token(db_engine)
    resp = await http_client.patch(
        f"/admin/users/{buyer}", json={"role": "admin"}, headers=_auth(admin)
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_suspend_blocks_login_and_revokes_sessions(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08070000001", email="h1@example.com"
    )
    _, admin = _staff_token(db_engine)
    before = await http_client.post(
        "/auth/login", json={"identifier": "h1@example.com", "password": _PASSWORD}
    )
    assert before.status_code == 200
    refresh_token = before.json()["refresh_token"]

    resp = await http_client.post(
        f"/admin/users/{buyer}/suspend", json={"reason": "chargeback fraud"}, headers=_auth(admin)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    # No new logins…
    after = await http_client.post(
        "/auth/login", json={"identifier": "h1@example.com", "password": _PASSWORD}
    )
    assert after.status_code == 401
    # …and the session they already held is gone, so "suspended" does not mean
    # "suspended in fifteen minutes".
    refreshed = await http_client.post("/auth/token/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 401

    reactivated = await http_client.post(f"/admin/users/{buyer}/reactivate", headers=_auth(admin))
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    again = await http_client.post(
        "/auth/login", json={"identifier": "h1@example.com", "password": _PASSWORD}
    )
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_delete_soft_deletes_and_frees_the_email(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
    deals_fake: InMemoryDealChecker,
) -> None:
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08080000001", email="i1@example.com"
    )
    _, admin = _staff_token(db_engine)

    resp = await http_client.request(
        "DELETE",
        f"/admin/users/{buyer}",
        json={"reason": "user asked by email"},
        headers=_auth(admin),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["sessions_revoked"] is True
    assert resp.json()["identifiers_released"] is True

    # Soft, not hard: the row survives for CBN/AMLON, with deleted_at set.
    with db_engine.connect() as conn:
        deleted_at = conn.execute(
            text("SELECT deleted_at FROM users WHERE id = :id"), {"id": buyer}
        ).scalar_one()
    assert deleted_at is not None

    # The guard asked about the TARGET, not the admin (SCRUM-209).
    assert deals_fake.subject_calls == [UUID(buyer)]

    # And the email is free again, so the person can sign up afresh.
    reused = await http_client.post(
        "/auth/register",
        json={"phone": "08080000009", "role": "buyer", "email": "i1@example.com"},
    )
    assert reused.status_code == 201, reused.text


@pytest.mark.asyncio
async def test_delete_refuses_when_the_target_has_active_deals(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
    deals_fake: InMemoryDealChecker,
) -> None:
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08090000001", email="j1@example.com"
    )
    _, admin = _staff_token(db_engine)
    deals_fake.active_for[UUID(buyer)] = True

    resp = await http_client.delete(f"/admin/users/{buyer}", headers=_auth(admin))

    assert resp.status_code == 409
    assert_error_envelope(resp.json(), "USER_HAS_ACTIVE_DEALS")
    with db_engine.connect() as conn:
        deleted_at = conn.execute(
            text("SELECT deleted_at FROM users WHERE id = :id"), {"id": buyer}
        ).scalar_one()
    assert deleted_at is None


@pytest.mark.asyncio
async def test_delete_fails_closed_when_the_check_is_unavailable(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
    deals_fake: InMemoryDealChecker,
) -> None:
    """503 and NOTHING deleted. Deleting an account whose escrow we could not
    check is unrecoverable; making the admin retry costs a minute."""
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08100000001", email="k1@example.com"
    )
    _, admin = _staff_token(db_engine)
    deals_fake.fail_next = True

    resp = await http_client.delete(f"/admin/users/{buyer}", headers=_auth(admin))

    assert resp.status_code == 503
    assert_error_envelope(resp.json(), "DELETE_CHECK_UNAVAILABLE")
    with db_engine.connect() as conn:
        deleted_at = conn.execute(
            text("SELECT deleted_at FROM users WHERE id = :id"), {"id": buyer}
        ).scalar_one()
    assert deleted_at is None


@pytest.mark.asyncio
async def test_delete_refuses_staff_and_self(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    db_engine: Engine,
    deals_fake: InMemoryDealChecker,
) -> None:
    admin_id, admin = _staff_token(db_engine)
    legal_id, _ = _staff_token(db_engine, role="legal_team")

    staff = await http_client.delete(f"/admin/users/{legal_id}", headers=_auth(admin))
    assert staff.status_code == 403
    assert_error_envelope(staff.json(), "CANNOT_DELETE_STAFF")

    myself = await http_client.delete(f"/admin/users/{admin_id}", headers=_auth(admin))
    assert myself.status_code == 403
    assert_error_envelope(myself.json(), "CANNOT_DELETE_SELF")


@pytest.mark.asyncio
async def test_deleted_user_is_hidden_unless_asked_for(
    clean_auth_tables: None,
    disable_rate_limit: None,
    sms_fake: InMemoryTwilioClient,
    http_client: AsyncClient,
    db_engine: Engine,
    deals_fake: InMemoryDealChecker,
) -> None:
    buyer = await _register(
        http_client, sms_fake, role="buyer", phone="08110000001", email="l1@example.com"
    )
    _, admin = _staff_token(db_engine)
    assert (
        await http_client.delete(f"/admin/users/{buyer}", headers=_auth(admin))
    ).status_code == 200

    hidden = await http_client.get("/admin/users", headers=_auth(admin))
    assert buyer not in [i["id"] for i in hidden.json()["items"]]

    shown = await http_client.get("/admin/users?include_deleted=true", headers=_auth(admin))
    row = next(i for i in shown.json()["items"] if i["id"] == buyer)
    assert row["deleted"] is True

    # The DETAIL read still answers for a deleted account: "what happened to this
    # person" is exactly what an admin is asking.
    detail = await http_client.get(f"/admin/users/{buyer}", headers=_auth(admin))
    assert detail.status_code == 200
    assert detail.json()["deleted_at"] is not None


@pytest.mark.asyncio
async def test_unknown_user_is_404(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    _, admin = _staff_token(db_engine)
    resp = await http_client.get(f"/admin/users/{uuid4()}", headers=_auth(admin))
    assert resp.status_code == 404
    assert_error_envelope(resp.json(), "USER_NOT_FOUND")


@pytest.mark.asyncio
async def test_search_below_two_characters_is_422(
    clean_auth_tables: None,
    disable_rate_limit: None,
    http_client: AsyncClient,
    db_engine: Engine,
) -> None:
    """A single character matches most of the table — a slow scan returning
    something useless."""
    _, admin = _staff_token(db_engine)
    resp: Any = await http_client.get("/admin/users?search=a", headers=_auth(admin))
    assert resp.status_code == 422
