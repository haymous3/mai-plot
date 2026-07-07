"""GET /wallet/summary + /wallet/payments integration tests (SCRUM-95)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

_PRICE = 12_000_000_000


def _seed_deal_with_deposit(db_engine: Engine, *, buyer: UUID, seller: UUID, listing: UUID) -> UUID:
    """A deal with a completed buyer_deposit + a matching escrow credit."""
    tx_id, pe_id = uuid4(), uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, :price, 'payment_held')"
            ),
            {"id": tx_id, "lid": listing, "bid": buyer, "sid": seller, "price": _PRICE},
        )
        conn.execute(
            text(
                "INSERT INTO payment_events (id, idempotency_key, payer_id, transaction_id, "
                "amount_kobo, payment_type, provider, status) VALUES "
                "(:id, :ik, :payer, :tid, :amt, 'buyer_deposit', 'paystack', 'completed')"
            ),
            {"id": pe_id, "ik": uuid4(), "payer": buyer, "tid": tx_id, "amt": _PRICE},
        )
        conn.execute(
            text(
                """
                INSERT INTO escrow_ledger
                    (id, transaction_id, entry_type, amount_kobo, description,
                     payment_event_id, requires_dual_approval)
                VALUES (:id, :tid, 'credit', :amt, 'seed deposit', :peid, FALSE)
                """
            ),
            {"id": uuid4(), "tid": tx_id, "amt": _PRICE, "peid": pe_id},
        )
    return tx_id


@pytest.mark.asyncio
async def test_wallet_summary(
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
    listing = seed_listing(seller_id=seller)
    tx = _seed_deal_with_deposit(db_engine, buyer=buyer, seller=seller, listing=listing)

    resp = await http_client.get("/wallet/summary", headers=auth_header(mint_token(buyer, "buyer")))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["in_escrow_kobo"] == _PRICE
    assert body["escrow_deal_count"] == 1
    assert body["total_invested_kobo"] == _PRICE
    assert body["active_property_count"] == 1
    assert len(body["active_payments"]) == 1
    ap = body["active_payments"][0]
    assert ap["transaction_id"] == str(tx)
    assert ap["paid_kobo"] == _PRICE
    assert ap["total_kobo"] == _PRICE


@pytest.mark.asyncio
async def test_wallet_payments_history(
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
    listing = seed_listing(seller_id=seller)
    _seed_deal_with_deposit(db_engine, buyer=buyer, seller=seller, listing=listing)

    resp = await http_client.get(
        "/wallet/payments", headers=auth_header(mint_token(buyer, "buyer"))
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["payment_type"] == "buyer_deposit"
    assert data[0]["status"] == "completed"
    assert data[0]["amount_kobo"] == _PRICE


@pytest.mark.asyncio
async def test_wallet_is_scoped_to_caller(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[..., str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    other = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_deal_with_deposit(db_engine, buyer=buyer, seller=seller, listing=listing)

    resp = await http_client.get("/wallet/summary", headers=auth_header(mint_token(other, "buyer")))
    body = resp.json()
    assert body["in_escrow_kobo"] == 0
    assert body["total_invested_kobo"] == 0
    assert body["active_property_count"] == 0


@pytest.mark.asyncio
async def test_wallet_requires_authentication(clean_tables: None, http_client: AsyncClient) -> None:
    resp = await http_client.get("/wallet/summary")
    assert resp.status_code == 401
