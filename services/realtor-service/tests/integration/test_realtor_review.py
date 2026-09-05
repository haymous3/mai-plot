"""Integration tests for admin realtor review (SCRUM-71)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.adapters.registration_number import InMemoryRegistrationNumberIssuer

pytestmark = pytest.mark.asyncio


def _audit_action(db_engine: Engine, user_id: UUID) -> str | None:
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT action FROM audit_log WHERE entity_id = :id "
                "AND entity_type = 'realtor' ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": user_id},
        ).first()
    return row.action if row is not None else None


async def test_queue_requires_admin(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    assert (await http_client.get("/admin/realtors/queue")).status_code == 401
    realtor = seed_user(role="realtor")
    forbidden = await http_client.get(
        "/admin/realtors/queue", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert forbidden.status_code == 403


async def test_queue_lists_pending(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    pending = seed_realtor(status="pending")
    seed_realtor(status="approved")  # should not appear
    admin = seed_user(role="admin")

    resp = await http_client.get(
        "/admin/realtors/queue", headers=auth_header(mint_token(admin, "admin"))
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [str(pending)]


async def test_approve_sets_approved_and_audits(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_realtor(status="pending")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        f"/admin/realtors/{realtor}/review", json={"action": "approve"}, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["approval_status"] == "approved"
    assert _audit_action(db_engine, realtor) == "realtor.approved"


async def test_reject_without_reason_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_realtor(status="pending")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))
    resp = await http_client.post(
        f"/admin/realtors/{realtor}/review", json={"action": "reject"}, headers=admin_headers
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "REASON_REQUIRED"


async def test_reject_with_reason_sets_rejected(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_realtor(status="pending")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))
    resp = await http_client.post(
        f"/admin/realtors/{realtor}/review",
        json={"action": "reject", "reason": "ID illegible"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "rejected"


async def test_suspend_non_approved_is_409(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_realtor(status="pending")  # not approved
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))
    resp = await http_client.post(
        f"/admin/realtors/{realtor}/review",
        json={"action": "suspend", "reason": "fraud"},
        headers=admin_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "REALTOR_NOT_ACTIONABLE"


async def test_review_unknown_realtor_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))
    resp = await http_client.post(
        f"/admin/realtors/{uuid4()}/review", json={"action": "approve"}, headers=admin_headers
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "REALTOR_NOT_FOUND"


# --- Maihomme registration number (SCRUM-207) --------------------------------


async def test_approve_returns_and_records_the_registration_number(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    registration_number_fake: InMemoryRegistrationNumberIssuer,
) -> None:
    realtor = seed_realtor(status="pending")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        f"/admin/realtors/{realtor}/review", json={"action": "approve"}, headers=admin_headers
    )

    assert resp.status_code == 200, resp.text
    number = resp.json()["registration_number"]
    assert number == registration_number_fake.issued[realtor]
    # In the audit row too: what the realtor was told is part of the decision's
    # history, not just of the email.
    with db_engine.connect() as conn:
        new_value = conn.execute(
            text(
                "SELECT new_value FROM audit_log WHERE entity_id = :id "
                "AND action = 'realtor.approved' ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": realtor},
        ).scalar_one()
    assert new_value["registration_number"] == number


async def test_issuance_failure_is_503_and_leaves_the_realtor_pending(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    registration_number_fake: InMemoryRegistrationNumberIssuer,
) -> None:
    """Fail closed. Approving without a number strands the realtor: they cannot
    sign in by number (none exists) or by email (refused once approved)."""
    realtor = seed_realtor(status="pending")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))
    registration_number_fake.fail_next = True

    resp = await http_client.post(
        f"/admin/realtors/{realtor}/review", json={"action": "approve"}, headers=admin_headers
    )

    assert resp.status_code == 503
    assert resp.json()["error_code"] == "REGISTRATION_NUMBER_UNAVAILABLE"
    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT approval_status FROM realtors WHERE id = :id"), {"id": realtor}
        ).scalar_one()
    assert status == "pending"
    assert _audit_action(db_engine, realtor) is None

    # And the admin can simply try again.
    retry = await http_client.post(
        f"/admin/realtors/{realtor}/review", json={"action": "approve"}, headers=admin_headers
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["registration_number"]


async def test_reject_issues_no_number(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
    registration_number_fake: InMemoryRegistrationNumberIssuer,
) -> None:
    realtor = seed_realtor(status="pending")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.post(
        f"/admin/realtors/{realtor}/review",
        json={"action": "reject", "reason": "ID illegible"},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["registration_number"] is None
    assert registration_number_fake.calls == []


async def test_queue_shows_the_applicants_name(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """With ESVARBON no longer collected, the name is the only thing identifying
    the row an admin is deciding on."""
    named = seed_realtor(status="pending", full_name="Ada Okafor")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get("/admin/realtors/queue", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["id"] == str(named))
    assert item["full_name"] == "Ada Okafor"


async def test_queue_keeps_an_applicant_with_no_pii_row(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """LEFT JOIN, not JOIN — a missing name must not drop the application off the
    review list. Hiding work is worse than showing a blank."""
    anonymous = seed_realtor(status="pending")
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get("/admin/realtors/queue", headers=admin_headers)

    ids = [i["id"] for i in resp.json()["items"]]
    assert str(anonymous) in ids
    item = next(i for i in resp.json()["items"] if i["id"] == str(anonymous))
    assert item["full_name"] is None
