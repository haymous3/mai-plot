"""Integration tests for admin realtor review (SCRUM-71)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

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
