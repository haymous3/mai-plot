"""GET /offers seller-inbox integration tests (SCRUM-98)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _seed_offer(
    engine: Engine,
    *,
    listing_id: UUID,
    buyer_id: UUID,
    offered_price_kobo: int = 4_200_000_000,
    status: str = "pending",
    note: str | None = None,
) -> UUID:
    offer_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO offers
                    (id, listing_id, buyer_id, offered_price_kobo, note, status, expires_at)
                VALUES (:id, :lid, :bid, :price, :note, :status, :exp)
                """
            ),
            {
                "id": offer_id,
                "lid": listing_id,
                "bid": buyer_id,
                "price": offered_price_kobo,
                "note": note,
                "status": status,
                "exp": datetime.now(UTC) + timedelta(days=3),
            },
        )
    return offer_id


@pytest.mark.asyncio
async def test_lists_only_my_offers(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    other_seller = seed_user(role="seller")
    buyer = seed_user(role="buyer")
    my_listing = seed_listing(seller_id=seller)
    other_listing = seed_listing(seller_id=other_seller)

    _seed_offer(db_engine, listing_id=my_listing, buyer_id=buyer, note="Ready to proceed.")
    _seed_offer(db_engine, listing_id=my_listing, buyer_id=buyer, status="accepted")
    _seed_offer(db_engine, listing_id=other_listing, buyer_id=buyer)

    resp = await http_client.get("/offers", headers=auth_header(mint_token(seller, "seller")))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 2
    # Scoped to this seller, buyer masked, asking price from the listing.
    item = next(i for i in data if i["note"] == "Ready to proceed.")
    assert item["buyer_ref"] == str(buyer)[:8]
    assert item["asking_price_kobo"] == 5_000_000_000
    assert item["offered_price_kobo"] == 4_200_000_000


@pytest.mark.asyncio
async def test_offers_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.get("/offers")
    assert resp.status_code == 401
