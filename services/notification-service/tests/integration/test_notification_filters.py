"""SCRUM-194 — category tabs and search on GET /notifications.

Both filters are applied in SQL rather than after the page is cut, because a
post-fetch filter would return short pages and corrupt the keyset cursor: the
cursor assumes the rows it skips past are the rows the caller actually saw.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _types(http_client: AsyncClient, token: str, query: str = "") -> list[str]:
    resp = await http_client.get(f"/notifications{query}", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return [i["type"] for i in resp.json()["items"]]


@pytest.mark.asyncio
async def test_category_narrows_the_feed_to_that_tab(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received", title="New offer")
    seed_notification(user_id=user, type="document_verified", title="Docs verified")
    seed_notification(user_id=user, type="listing_approved", title="Listing live")

    assert set(await _types(http_client, token, "?category=bids")) == {"offer_received"}
    assert set(await _types(http_client, token, "?category=documents")) == {"document_verified"}


@pytest.mark.asyncio
async def test_no_category_is_the_all_tab(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received")
    seed_notification(user_id=user, type="document_verified")

    assert len(await _types(http_client, token)) == 2


@pytest.mark.asyncio
async def test_system_is_a_catch_all_and_includes_unmapped_types(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    """A type nobody mapped must still be reachable. System filters by NOT IN
    the other tabs precisely so a new producer cannot go invisible."""
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="listing_approved")
    seed_notification(user_id=user, type="a_type_shipped_after_this_ticket")
    seed_notification(user_id=user, type="offer_received")

    found = set(await _types(http_client, token, "?category=system"))
    assert found == {"listing_approved", "a_type_shipped_after_this_ticket"}
    assert "offer_received" not in found


@pytest.mark.asyncio
async def test_an_unknown_category_is_rejected_not_silently_empty(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    """An empty list would read as "you have nothing" rather than "that is not
    a tab"."""
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")

    resp = await http_client.get("/notifications?category=messages", headers=_auth(token))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_matches_title_and_body(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received", title="Lekki Phase 1", body="x")
    seed_notification(user_id=user, type="offer_accepted", title="Ikoyi", body="Lekki duplex")
    seed_notification(user_id=user, type="listing_approved", title="Ajah", body="nothing here")

    found = set(await _types(http_client, token, "?q=lekki"))
    assert found == {"offer_received", "offer_accepted"}


@pytest.mark.asyncio
async def test_search_treats_a_percent_as_a_literal_not_a_wildcard(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    """Unescaped, a user's own `%` would silently widen their search to match
    everything — the wrong rows, which is worse than no rows."""
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received", title="100% funded", body="x")
    seed_notification(user_id=user, type="listing_approved", title="unrelated", body="y")

    assert set(await _types(http_client, token, "?q=100%25")) == {"offer_received"}
    # Searching for a bare "%" finds rows CONTAINING a percent sign — it does
    # not match everything. Were it still a wildcard both rows would come back,
    # so this is the assertion that actually pins the escaping down.
    assert set(await _types(http_client, token, "?q=%25")) == {"offer_received"}


@pytest.mark.asyncio
async def test_search_treats_an_underscore_as_a_literal(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received", title="deed_of_assignment", body="x")
    seed_notification(user_id=user, type="listing_approved", title="deedXof", body="y")

    assert set(await _types(http_client, token, "?q=deed_of")) == {"offer_received"}


@pytest.mark.asyncio
async def test_a_blank_search_is_no_search(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    """Clearing the box must return the whole feed, not run an ILIKE '%%'."""
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received")
    seed_notification(user_id=user, type="listing_approved")

    assert len(await _types(http_client, token, "?q=")) == 2
    assert len(await _types(http_client, token, "?q=%20%20")) == 2


@pytest.mark.asyncio
async def test_category_and_search_combine(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received", title="Lekki offer", body="x")
    seed_notification(user_id=user, type="listing_approved", title="Lekki listing", body="y")

    found = set(await _types(http_client, token, "?category=bids&q=lekki"))
    assert found == {"offer_received"}


@pytest.mark.asyncio
async def test_the_unread_badge_stays_whole_inbox_while_a_tab_is_open(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    """A badge that shrank when you opened a tab would be saying something
    false about the rest of the inbox."""
    user = seed_user(phone="08012345678")
    token = mint_token(user, "seller")
    seed_notification(user_id=user, type="offer_received", is_read=False)
    seed_notification(user_id=user, type="document_verified", is_read=False)
    seed_notification(user_id=user, type="listing_approved", is_read=False)

    resp = await http_client.get("/notifications?category=bids", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()

    assert len(body["items"]) == 1
    assert body["unread_count"] == 3
    assert resp.headers["X-Unread-Count"] == "3"


@pytest.mark.asyncio
async def test_a_filtered_feed_still_only_shows_the_callers_own_rows(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
) -> None:
    """The filters narrow a feed that is already scoped to the caller; neither
    may widen it."""
    mine = seed_user(phone="08012345678")
    theirs = seed_user(phone="08011112222")
    token = mint_token(mine, "seller")
    seed_notification(user_id=theirs, type="offer_received", title="Lekki", body="x")

    assert await _types(http_client, token, "?category=bids") == []
    assert await _types(http_client, token, "?q=lekki") == []
