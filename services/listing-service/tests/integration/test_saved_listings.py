"""Saved-listings integration tests (SCRUM-95): POST/DELETE /listings/{id}/save
+ GET /listings/saved."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


def _auth(mint: Callable[..., str], user_id: UUID, role: str = "buyer") -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(user_id, role)}"}


@pytest.mark.asyncio
async def test_save_then_list_then_unsave(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller, title="Saved Plot")
    buyer = seed_seller(phone="08099999999", role="buyer", seller_authority_type=None)
    headers = _auth(mint_access_token, buyer)

    saved = await http_client.post(f"/listings/{listing}/save", headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"listing_id": str(listing), "saved": True}

    listed = await http_client.get("/listings/saved", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert [i["title"] for i in body["data"]] == ["Saved Plot"]

    removed = await http_client.delete(f"/listings/{listing}/save", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["saved"] is False

    empty = await http_client.get("/listings/saved", headers=headers)
    assert empty.json()["data"] == []


@pytest.mark.asyncio
async def test_save_is_idempotent_and_resavable(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller, title="Plot")
    buyer = seed_seller(phone="08088888888", role="buyer", seller_authority_type=None)
    headers = _auth(mint_access_token, buyer)

    await http_client.post(f"/listings/{listing}/save", headers=headers)
    await http_client.post(f"/listings/{listing}/save", headers=headers)  # duplicate
    listed = await http_client.get("/listings/saved", headers=headers)
    assert len(listed.json()["data"]) == 1  # unique(buyer, listing) — no dupes

    await http_client.delete(f"/listings/{listing}/save", headers=headers)
    await http_client.post(f"/listings/{listing}/save", headers=headers)  # re-save
    relisted = await http_client.get("/listings/saved", headers=headers)
    assert len(relisted.json()["data"]) == 1  # deleted_at cleared, not a new row


@pytest.mark.asyncio
async def test_saved_is_per_buyer(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller, title="Plot")
    buyer_a = seed_seller(phone="08010000001", role="buyer", seller_authority_type=None)
    buyer_b = seed_seller(phone="08010000002", role="buyer", seller_authority_type=None)

    await http_client.post(f"/listings/{listing}/save", headers=_auth(mint_access_token, buyer_a))

    a = await http_client.get("/listings/saved", headers=_auth(mint_access_token, buyer_a))
    b = await http_client.get("/listings/saved", headers=_auth(mint_access_token, buyer_b))
    assert len(a.json()["data"]) == 1
    assert b.json()["data"] == []


@pytest.mark.asyncio
async def test_save_requires_authentication(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[[dict[str, Any], str], None],
) -> None:
    resp = await http_client.post(f"/listings/{uuid4()}/save")
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
