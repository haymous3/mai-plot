"""POST /listings/{id}/interest integration tests (SCRUM-95)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _auth(mint: Callable[..., str], user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(user_id, 'buyer')}"}


def _interest_count(db_engine: Engine, listing_id: UUID) -> int:
    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT interest_count FROM property_listings WHERE id = :id"),
            {"id": listing_id},
        ).scalar_one()
    return int(count)


@pytest.mark.asyncio
async def test_express_interest_bumps_count_once(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller)
    buyer = seed_seller(phone="08099999999", role="buyer", seller_authority_type=None)
    headers = _auth(mint_access_token, buyer)
    assert _interest_count(db_engine, listing) == 0

    first = await http_client.post(
        f"/listings/{listing}/interest", json={"message": "Interested!"}, headers=headers
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"listing_id": str(listing), "new_interest": True}
    assert _interest_count(db_engine, listing) == 1

    # A repeat interest is idempotent — no second count.
    second = await http_client.post(f"/listings/{listing}/interest", json={}, headers=headers)
    assert second.status_code == 200
    assert second.json()["new_interest"] is False
    assert _interest_count(db_engine, listing) == 1


@pytest.mark.asyncio
async def test_interest_count_is_per_buyer(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_access_token: Callable[..., str],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing = seed_listing(seller_id=seller)
    buyer_a = seed_seller(phone="08010000001", role="buyer", seller_authority_type=None)
    buyer_b = seed_seller(phone="08010000002", role="buyer", seller_authority_type=None)

    await http_client.post(
        f"/listings/{listing}/interest", json={}, headers=_auth(mint_access_token, buyer_a)
    )
    await http_client.post(
        f"/listings/{listing}/interest", json={}, headers=_auth(mint_access_token, buyer_b)
    )
    assert _interest_count(db_engine, listing) == 2


@pytest.mark.asyncio
async def test_interest_requires_authentication(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    assert_error_envelope: Callable[..., None],
) -> None:
    resp = await http_client.post(f"/listings/{uuid4()}/interest", json={})
    assert resp.status_code == 401
    assert_error_envelope(resp.json(), "UNAUTHORIZED")
