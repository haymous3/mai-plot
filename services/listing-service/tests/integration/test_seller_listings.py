"""GET /listings/mine + pause/resume integration tests (SCRUM-98)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient


def _auth(mint: Callable[..., str], user_id: UUID, role: str = "seller") -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(user_id, role)}"}


@pytest.mark.asyncio
async def test_lists_only_my_listings(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    other = seed_seller(phone="08099999999")
    seed_listing(seller_id=seller, title="Mine A")
    seed_listing(seller_id=seller, title="Mine B", status="paused")
    seed_listing(seller_id=other, title="Not mine")

    resp = await http_client.get("/listings/mine", headers=_auth(mint_access_token, seller))
    assert resp.status_code == 200, resp.text
    titles = {i["title"] for i in resp.json()["data"]}
    assert titles == {"Mine A", "Mine B"}
    # Counts are present (offers/saves default 0).
    row = next(i for i in resp.json()["data"] if i["title"] == "Mine A")
    assert row["offers_count"] == 0
    assert row["saves_count"] == 0


@pytest.mark.asyncio
async def test_pause_and_resume(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller, status="active")
    headers = _auth(mint_access_token, seller)

    paused = await http_client.post(f"/listings/{listing}/pause", headers=headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"

    resumed = await http_client.post(f"/listings/{listing}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"


@pytest.mark.asyncio
async def test_pause_not_owner_forbidden(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    stranger = seed_seller(phone="08088888888")
    listing = seed_listing(seller_id=seller, status="active")

    resp = await http_client.post(
        f"/listings/{listing}/pause", headers=_auth(mint_access_token, stranger)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_my_listings_requires_authentication(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[..., None],
) -> None:
    resp = await http_client.get("/listings/mine")
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
