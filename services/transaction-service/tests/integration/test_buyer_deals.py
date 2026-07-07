"""GET /transactions (buyer deals list) integration tests (SCRUM-95)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _seed_transaction(
    db_engine: Engine, *, buyer: UUID, seller: UUID, listing: UUID, price: int, stage: str
) -> UUID:
    tx_id = uuid4()
    with db_engine.begin() as conn:
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
                "price": price,
                "stage": stage,
            },
        )
    return tx_id


@pytest.mark.asyncio
async def test_lists_buyer_deals_with_property_title(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[..., str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)  # seeds title 'Plot'
    _seed_transaction(
        db_engine,
        buyer=buyer,
        seller=seller,
        listing=listing,
        price=4_800_000_000,
        stage="offer_accepted",
    )

    resp = await http_client.get("/transactions", headers=auth_header(mint_token(buyer, "buyer")))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["property_title"] == "Plot"
    assert data[0]["listing_id"] == str(listing)
    assert data[0]["stage"] == "offer_accepted"
    assert data[0]["agreed_price_kobo"] == 4_800_000_000


@pytest.mark.asyncio
async def test_deals_are_scoped_to_the_caller(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[..., str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer_a = seed_user(role="buyer")
    buyer_b = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_transaction(
        db_engine,
        buyer=buyer_a,
        seller=seller,
        listing=listing,
        price=1_000_000_000,
        stage="loan_applied",
    )

    a = await http_client.get("/transactions", headers=auth_header(mint_token(buyer_a, "buyer")))
    b = await http_client.get("/transactions", headers=auth_header(mint_token(buyer_b, "buyer")))
    assert len(a.json()["data"]) == 1
    assert b.json()["data"] == []


@pytest.mark.asyncio
async def test_requires_authentication(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.get("/transactions")
    assert resp.status_code == 401
