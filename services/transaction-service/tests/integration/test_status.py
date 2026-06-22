"""Transaction status PATCH integration tests (SCRUM-67)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _seed_transaction(
    db_engine: Engine,
    *,
    buyer_id: UUID,
    seller_id: UUID,
    listing_id: UUID | None = None,
    stage: str = "offer_accepted",
) -> UUID:
    txn_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO transactions
                    (id, listing_id, buyer_id, seller_id, agreed_price_kobo, stage)
                VALUES (:id, :lid, :bid, :sid, 5000000000, :stage)
                """
            ),
            {
                "id": txn_id,
                "lid": listing_id or uuid4(),
                "bid": buyer_id,
                "sid": seller_id,
                "stage": stage,
            },
        )
    return txn_id


@pytest.mark.asyncio
async def test_valid_transition_updates_stage_event_and_audit(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    txn_id = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)

    response = await http_client.patch(
        f"/transactions/{txn_id}/status",
        json={"status": "inspection_scheduled"},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "inspection_scheduled"

    with db_engine.connect() as conn:
        stage = conn.execute(
            text("SELECT stage FROM transactions WHERE id = :id"), {"id": txn_id}
        ).scalar_one()
        assert stage == "inspection_scheduled"

        event = conn.execute(
            text("SELECT from_stage, to_stage FROM transaction_events WHERE transaction_id = :id"),
            {"id": txn_id},
        ).first()
        assert event is not None
        assert event.from_stage == "offer_accepted"
        assert event.to_stage == "inspection_scheduled"

        audit = conn.execute(
            text(
                "SELECT action FROM audit_log "
                "WHERE entity_id = :id AND action = 'transaction.inspection_scheduled'"
            ),
            {"id": txn_id},
        ).first()
        assert audit is not None


@pytest.mark.asyncio
async def test_illegal_transition_is_422(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    txn_id = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)

    response = await http_client.patch(
        f"/transactions/{txn_id}/status",
        json={"status": "completed"},  # offer_accepted -> completed is illegal
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_arbitrary_stage_value_is_rejected(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    txn_id = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)

    response = await http_client.patch(
        f"/transactions/{txn_id}/status",
        json={"status": "totally_made_up"},
        headers=auth_header(mint_token(buyer, "buyer")),
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_non_party_is_forbidden(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    stranger = seed_user(role="buyer")
    txn_id = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)

    response = await http_client.patch(
        f"/transactions/{txn_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(mint_token(stranger, "buyer")),
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "NOT_TRANSACTION_PARTY"


@pytest.mark.asyncio
async def test_cancel_reopens_the_listing(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing_id = seed_listing(seller_id=seller, status="under_offer")
    txn_id = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller, listing_id=listing_id)

    response = await http_client.patch(
        f"/transactions/{txn_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(mint_token(seller, "seller")),
    )
    assert response.status_code == 200, response.text

    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
        ).scalar_one()
        assert status == "active"  # lock released


@pytest.mark.asyncio
async def test_complete_marks_the_listing_sold(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing_id = seed_listing(seller_id=seller, status="under_offer")
    txn_id = _seed_transaction(
        db_engine, buyer_id=buyer, seller_id=seller, listing_id=listing_id, stage="title_held"
    )

    response = await http_client.patch(
        f"/transactions/{txn_id}/status",
        json={"status": "completed"},
        headers=auth_header(mint_token(seller, "seller")),
    )
    assert response.status_code == 200, response.text

    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
        ).scalar_one()
        assert status == "sold"


@pytest.mark.asyncio
async def test_complete_persists_the_platform_fee(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing_id = seed_listing(seller_id=seller, status="under_offer")
    txn_id = _seed_transaction(
        db_engine, buyer_id=buyer, seller_id=seller, listing_id=listing_id, stage="title_held"
    )

    response = await http_client.patch(
        f"/transactions/{txn_id}/status",
        json={"status": "completed"},
        headers=auth_header(mint_token(seller, "seller")),
    )
    assert response.status_code == 200, response.text

    with db_engine.connect() as conn:
        # Seeded agreed price is 5,000,000,000 kobo; default 2.5% = 125,000,000.
        fee = conn.execute(
            text("SELECT platform_fee_kobo FROM transactions WHERE id = :id"), {"id": txn_id}
        ).scalar_one()
        assert fee == 125_000_000

        audit = conn.execute(
            text(
                "SELECT action FROM audit_log "
                "WHERE entity_id = :id AND action = 'transaction.platform_fee_set'"
            ),
            {"id": txn_id},
        ).first()
        assert audit is not None


@pytest.mark.asyncio
async def test_status_requires_authentication(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    txn_id = _seed_transaction(db_engine, buyer_id=buyer, seller_id=seller)
    response = await http_client.patch(
        f"/transactions/{txn_id}/status", json={"status": "cancelled"}
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"
