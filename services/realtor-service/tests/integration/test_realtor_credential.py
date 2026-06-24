"""Integration tests for admin gov-ID credential viewing (SCRUM-62)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.asyncio


def _credential_audit_count(db_engine: Engine, user_id: UUID) -> int:
    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM audit_log WHERE entity_id = :id "
                "AND action = 'realtor.credential_viewed'"
            ),
            {"id": user_id},
        ).scalar_one()
    return int(count)


async def test_returns_presigned_url_and_audits(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_realtor(status="pending")  # seeded with government_id_s3_key
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get(f"/admin/realtors/{realtor}/government-id", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    # In-memory storage fake mints a memory:// URL for the realtor's ID key.
    assert resp.json()["url"].startswith("memory://documents/realtor-id/")
    assert _credential_audit_count(db_engine, realtor) == 1


async def test_requires_admin(
    clean_tables: None,
    http_client: AsyncClient,
    seed_realtor: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_realtor(status="pending")
    assert (await http_client.get(f"/admin/realtors/{realtor}/government-id")).status_code == 401
    forbidden = await http_client.get(
        f"/admin/realtors/{realtor}/government-id",
        headers=auth_header(mint_token(seed_user(role="realtor"), "realtor")),
    )
    assert forbidden.status_code == 403


async def test_unknown_realtor_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))
    resp = await http_client.get(f"/admin/realtors/{uuid4()}/government-id", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "REALTOR_NOT_FOUND"


async def test_no_document_on_file_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    # A realtor row with a NULL government_id_s3_key (legacy/edge case).
    realtor = seed_user(role="realtor")
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO realtors (id, esvarbon_number, coverage_states, approval_status) "
                "VALUES (:id, :esv, ARRAY['Lagos'], 'pending')"
            ),
            {"id": realtor, "esv": f"ESV/{uuid4().hex[:8].upper()}"},
        )
    admin_headers = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get(f"/admin/realtors/{realtor}/government-id", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "CREDENTIAL_UNAVAILABLE"
