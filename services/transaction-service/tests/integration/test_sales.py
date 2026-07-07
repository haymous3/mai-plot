"""GET /sales seller-transactions integration tests (SCRUM-98)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _seed_tx(
    engine: Engine, *, buyer: UUID, seller: UUID, listing: UUID, stage: str = "payment_held"
) -> UUID:
    tx_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, :price, :stage)"
            ),
            {
                "id": tx_id,
                "lid": listing,
                "bid": buyer,
                "sid": seller,
                "price": 12_000_000_000,
                "stage": stage,
            },
        )
    return tx_id


@pytest.mark.asyncio
async def test_lists_only_my_sales(
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
    mine = seed_listing(seller_id=seller)
    theirs = seed_listing(seller_id=other_seller)

    _seed_tx(db_engine, buyer=buyer, seller=seller, listing=mine)
    _seed_tx(db_engine, buyer=buyer, seller=other_seller, listing=theirs)

    resp = await http_client.get("/sales", headers=auth_header(mint_token(seller, "seller")))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["buyer_ref"] == str(buyer)[:8]
    assert data[0]["agreed_price_kobo"] == 12_000_000_000
    assert data[0]["property_title"] == "Plot"


@pytest.mark.asyncio
async def test_sales_requires_auth(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.get("/sales")
    assert resp.status_code == 401
