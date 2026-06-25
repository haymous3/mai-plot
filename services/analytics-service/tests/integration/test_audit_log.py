"""Integration tests for the admin audit-log viewer (SCRUM-126)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_BASE = "/admin/analytics/audit-log"


async def test_requires_admin(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    assert (await http_client.get(_BASE)).status_code == 401
    non_admin = seed_user(role="buyer")
    forbidden = await http_client.get(_BASE, headers=auth_header(mint_token(non_admin, "buyer")))
    assert forbidden.status_code == 403
    assert forbidden.json()["error_code"] == "ADMIN_FORBIDDEN"


async def test_lists_newest_first_and_paginates(
    clean_tables: None,
    http_client: AsyncClient,
    seed_audit: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    base = datetime.now(UTC) - timedelta(hours=1)
    oldest = seed_audit(action="listing.created", created_at=base)
    middle = seed_audit(action="listing.approved", created_at=base + timedelta(minutes=10))
    newest = seed_audit(action="listing.rejected", created_at=base + timedelta(minutes=20))
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    page1 = await http_client.get(f"{_BASE}?page_size=2", headers=admin)
    assert page1.status_code == 200, page1.text
    body = page1.json()
    assert [i["id"] for i in body["items"]] == [str(newest), str(middle)]  # newest-first
    assert body["pagination"] == {"page": 1, "page_size": 2, "total": 3, "total_pages": 2}

    page2 = await http_client.get(f"{_BASE}?page_size=2&page=2", headers=admin)
    assert [i["id"] for i in page2.json()["items"]] == [str(oldest)]


async def test_filter_by_entity_type(
    clean_tables: None,
    http_client: AsyncClient,
    seed_audit: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seed_audit(entity_type="listing", action="listing.approved")
    realtor_event = seed_audit(entity_type="realtor", action="realtor.approved")
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get(f"{_BASE}?entity_type=realtor", headers=admin)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [str(realtor_event)]
    assert items[0]["entity_type"] == "realtor"


async def test_filter_by_actor(
    clean_tables: None,
    http_client: AsyncClient,
    seed_audit: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    actor = seed_user(role="admin")
    mine = seed_audit(actor_id=actor, action="realtor.suspended")
    seed_audit(actor_id=None, action="listing.approved")  # no actor
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    resp = await http_client.get(f"{_BASE}?actor_id={actor}", headers=admin)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [str(mine)]
    assert items[0]["actor_id"] == str(actor)


async def test_filter_by_action_and_empty_result(
    clean_tables: None,
    http_client: AsyncClient,
    seed_audit: Callable[..., UUID],
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seed_audit(action="listing.approved")
    admin = auth_header(mint_token(seed_user(role="admin"), "admin"))

    hit = await http_client.get(f"{_BASE}?action=listing.approved", headers=admin)
    assert len(hit.json()["items"]) == 1

    miss = await http_client.get(f"{_BASE}?action=nope.nothing", headers=admin)
    assert miss.status_code == 200
    assert miss.json()["items"] == []
    assert miss.json()["pagination"] == {
        "page": 1,
        "page_size": 50,
        "total": 0,
        "total_pages": 0,
    }
