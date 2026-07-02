"""Integration tests for GET /transactions/{id}/financing-summary (SCRUM-94)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.asyncio

_PRICE = 6_000_000_000  # ₦60M


def _seed_transaction(db_engine: Engine, *, buyer: UUID, seller: UUID, listing: UUID) -> UUID:
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, :price, "
                "'inspection_completed')"
            ),
            {"id": tx_id, "lid": listing, "bid": buyer, "sid": seller, "price": _PRICE},
        )
    return tx_id


async def test_buyer_sees_property_price_and_cap(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    buyer = seed_user(role="buyer")
    listing = seed_listing(seller_id=seller)
    tx = _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing)

    resp = await http_client.get(
        f"/transactions/{tx}/financing-summary", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agreed_price_kobo"] == _PRICE
    assert body["max_loan_kobo"] == _PRICE // 2  # 50% cap
    assert body["property"]["title"] == "Plot"
    assert body["property"]["primary_image_url"] is None  # no media seeded
    assert body["existing_loan"] is None


async def test_stranger_forbidden(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    buyer = seed_user(role="buyer")
    listing = seed_listing(seller_id=seller)
    tx = _seed_transaction(db_engine, buyer=buyer, seller=seller, listing=listing)

    stranger = seed_user(role="buyer")
    resp = await http_client.get(
        f"/transactions/{tx}/financing-summary",
        headers=auth_header(mint_token(stranger, "buyer")),
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "NOT_TRANSACTION_BUYER"


async def test_unknown_transaction_404(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    resp = await http_client.get(
        f"/transactions/{uuid4()}/financing-summary",
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "TRANSACTION_NOT_FOUND"
