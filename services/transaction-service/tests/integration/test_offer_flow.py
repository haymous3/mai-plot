"""Offer flow integration tests (SCRUM-66) — real DB + JWT."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.mark.asyncio
async def test_create_then_accept_offer_creates_transaction(
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
    listing_id = seed_listing(seller_id=seller)

    # Buyer makes an offer.
    create = await http_client.post(
        "/transactions",
        json={"listing_id": str(listing_id), "amount_kobo": 4_000_000_000},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert create.status_code == 201, create.text
    offer = create.json()
    assert offer["status"] == "pending"
    offer_id = offer["id"]

    # Seller accepts.
    accept = await http_client.post(
        f"/transactions/{offer_id}/accept", headers=auth_header(mint_token(seller, "seller"))
    )
    assert accept.status_code == 200, accept.text
    body = accept.json()
    assert body["status"] == "accepted"
    assert body["transaction_id"] is not None

    with db_engine.connect() as conn:
        txn = conn.execute(
            text("SELECT stage, agreed_price_kobo FROM transactions WHERE id = :id"),
            {"id": body["transaction_id"]},
        ).first()
        assert txn is not None
        assert txn.stage == "offer_accepted"
        assert txn.agreed_price_kobo == 4_000_000_000

        event = conn.execute(
            text(
                "SELECT to_stage FROM transaction_events "
                "WHERE transaction_id = :id AND event_type = 'offer_accepted'"
            ),
            {"id": body["transaction_id"]},
        ).first()
        assert event is not None and event.to_stage == "offer_accepted"

        listing = conn.execute(
            text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
        ).first()
        assert listing is not None and listing.status == "under_offer"


@pytest.mark.asyncio
async def test_cannot_offer_on_own_listing(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    listing_id = seed_listing(seller_id=seller)
    response = await http_client.post(
        "/transactions",
        json={"listing_id": str(listing_id), "amount_kobo": 1_000_000_000},
        headers=auth_header(mint_token(seller, "seller")),
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "CANNOT_OFFER_OWN_LISTING"


@pytest.mark.asyncio
async def test_offer_on_under_offer_listing_conflicts(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    buyer = seed_user(role="buyer")
    listing_id = seed_listing(seller_id=seller, status="under_offer")
    response = await http_client.post(
        "/transactions",
        json={"listing_id": str(listing_id), "amount_kobo": 1_000_000_000},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "LISTING_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_new_offer_allowed_after_72h_lock_lapses(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_user(role="seller")
    first_buyer = seed_user(role="buyer")
    second_buyer = seed_user(role="buyer")
    listing_id = seed_listing(seller_id=seller, status="under_offer")
    # A transaction whose 72h lock has already lapsed, still parked at
    # offer_accepted (the first buyer never progressed).
    stale_txn = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO transactions
                    (id, listing_id, buyer_id, seller_id, agreed_price_kobo, stage,
                     lock_expires_at)
                VALUES (:id, :lid, :bid, :sid, 5000000000, 'offer_accepted',
                        NOW() - INTERVAL '1 hour')
                """
            ),
            {"id": stale_txn, "lid": listing_id, "bid": first_buyer, "sid": seller},
        )

    response = await http_client.post(
        "/transactions",
        json={"listing_id": str(listing_id), "amount_kobo": 4_000_000_000},
        headers=auth_header(mint_token(second_buyer, "buyer")),
    )
    assert response.status_code == 201, response.text  # lock lapsed → new offer allowed

    with db_engine.connect() as conn:
        stale_stage = conn.execute(
            text("SELECT stage FROM transactions WHERE id = :id"), {"id": stale_txn}
        ).scalar_one()
        assert stale_stage == "cancelled"  # abandoned deal cancelled

        listing_status = conn.execute(
            text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
        ).scalar_one()
        assert listing_status == "active"  # listing reopened (new offer is pending, not accepted)

        audit = conn.execute(
            text(
                "SELECT actor_role FROM audit_log "
                "WHERE entity_id = :id AND action = 'transaction.cancelled'"
            ),
            {"id": stale_txn},
        ).first()
        assert audit is not None and audit.actor_role == "system"


@pytest.mark.asyncio
async def test_counter_then_buyer_accepts(
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
    listing_id = seed_listing(seller_id=seller)

    create = await http_client.post(
        "/transactions",
        json={"listing_id": str(listing_id), "amount_kobo": 4_000_000_000},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    offer_id = create.json()["id"]

    counter = await http_client.post(
        f"/transactions/{offer_id}/counter",
        json={"counter_amount_kobo": 6_000_000_000},
        headers=auth_header(mint_token(seller, "seller")),
    )
    assert counter.status_code == 200, counter.text
    assert counter.json()["status"] == "countered"

    respond = await http_client.post(
        f"/transactions/{offer_id}/respond",
        json={"action": "accept"},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert respond.status_code == 200, respond.text
    assert respond.json()["status"] == "accepted"

    with db_engine.connect() as conn:
        price = conn.execute(
            text("SELECT agreed_price_kobo FROM transactions WHERE id = :id"),
            {"id": respond.json()["transaction_id"]},
        ).scalar_one()
        assert price == 6_000_000_000  # counter price, not the original


@pytest.mark.asyncio
async def test_offer_requires_authentication(
    clean_tables: None,
    http_client: AsyncClient,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    seller = seed_user(role="seller")
    listing_id = seed_listing(seller_id=seller)
    response = await http_client.post(
        "/transactions", json={"listing_id": str(listing_id), "amount_kobo": 1_000_000_000}
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"
