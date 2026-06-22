"""Integration tests for the in-app notification centre (SCRUM-82).

Real DB, real JWT. Covers listing newest-first, keyset pagination, per-user
scoping, mark-read (idempotent + 404), mark-all-read, the unread-count header,
and the auth gate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_requires_auth(http_client: AsyncClient, clean_tables: None) -> None:
    resp = await http_client.get("/notifications")
    assert resp.status_code == 401


async def test_list_returns_newest_first_with_unread_header(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="buyer")
    base = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    seed_notification(user_id=user_id, body="oldest", created_at=base)
    newest = seed_notification(user_id=user_id, body="newest", created_at=base + timedelta(hours=2))
    seed_notification(user_id=user_id, body="middle", created_at=base + timedelta(hours=1))

    resp = await http_client.get(
        "/notifications", headers=auth_header(mint_token(user_id, "buyer"))
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [item["body"] for item in body["items"]] == ["newest", "middle", "oldest"]
    assert body["items"][0]["id"] == str(newest)
    assert body["unread_count"] == 3
    assert resp.headers["X-Unread-Count"] == "3"
    assert body["next_cursor"] is None


async def test_list_paginates_via_cursor(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="buyer")
    base = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    for i in range(5):
        seed_notification(user_id=user_id, body=f"n{i}", created_at=base + timedelta(minutes=i))
    headers = auth_header(mint_token(user_id, "buyer"))

    first = await http_client.get("/notifications?limit=2", headers=headers)
    assert first.status_code == 200
    page1 = first.json()
    assert [it["body"] for it in page1["items"]] == ["n4", "n3"]
    assert page1["next_cursor"] is not None

    second = await http_client.get(
        f"/notifications?limit=2&cursor={page1['next_cursor']}", headers=headers
    )
    page2 = second.json()
    assert [it["body"] for it in page2["items"]] == ["n2", "n1"]
    assert page2["next_cursor"] is not None

    third = await http_client.get(
        f"/notifications?limit=2&cursor={page2['next_cursor']}", headers=headers
    )
    page3 = third.json()
    assert [it["body"] for it in page3["items"]] == ["n0"]
    assert page3["next_cursor"] is None


async def test_list_is_scoped_to_caller(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    alice = seed_user(role="buyer")
    bob = seed_user(role="buyer")
    seed_notification(user_id=alice, body="for alice")
    seed_notification(user_id=bob, body="for bob")

    resp = await http_client.get("/notifications", headers=auth_header(mint_token(bob, "buyer")))
    body = resp.json()
    assert [it["body"] for it in body["items"]] == ["for bob"]
    assert body["unread_count"] == 1


async def test_invalid_cursor_returns_400(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="buyer")
    resp = await http_client.get(
        "/notifications?cursor=not-valid", headers=auth_header(mint_token(user_id, "buyer"))
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_CURSOR"


async def test_mark_read_is_idempotent_and_updates_count(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="buyer")
    notif_id = seed_notification(user_id=user_id, body="hi", is_read=False)
    headers = auth_header(mint_token(user_id, "buyer"))

    first = await http_client.patch(f"/notifications/{notif_id}/read", headers=headers)
    assert first.status_code == 204
    # Idempotent — a second mark still succeeds.
    second = await http_client.patch(f"/notifications/{notif_id}/read", headers=headers)
    assert second.status_code == 204

    listed = await http_client.get("/notifications", headers=headers)
    body = listed.json()
    assert body["unread_count"] == 0
    assert body["items"][0]["is_read"] is True
    assert body["items"][0]["read_at"] is not None


async def test_mark_read_other_users_notification_is_404(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    alice = seed_user(role="buyer")
    bob = seed_user(role="buyer")
    alice_notif = seed_notification(user_id=alice, body="alice only")

    resp = await http_client.patch(
        f"/notifications/{alice_notif}/read", headers=auth_header(mint_token(bob, "buyer"))
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOTIFICATION_NOT_FOUND"


async def test_mark_unknown_notification_is_404(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="buyer")
    resp = await http_client.patch(
        f"/notifications/{uuid4()}/read", headers=auth_header(mint_token(user_id, "buyer"))
    )
    assert resp.status_code == 404


async def test_mark_all_read(
    http_client: AsyncClient,
    clean_tables: None,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    user_id = seed_user(role="buyer")
    seed_notification(user_id=user_id, body="a", is_read=False)
    seed_notification(user_id=user_id, body="b", is_read=False)
    seed_notification(user_id=user_id, body="c", is_read=True)
    headers = auth_header(mint_token(user_id, "buyer"))

    resp = await http_client.patch("/notifications/read-all", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["marked_read"] == 2

    listed = await http_client.get("/notifications", headers=headers)
    assert listed.json()["unread_count"] == 0
