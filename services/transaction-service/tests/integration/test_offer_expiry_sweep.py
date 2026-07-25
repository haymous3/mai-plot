"""Integration tests for the lapsed-offer sweep (SCRUM-118).

Seeds pending/countered offers past their window alongside a live pending offer
and an accepted one, runs the sweep, and asserts only the lapsed live offers are
stamped 'expired' — accepted/rejected and still-live offers are untouched.
Idempotent across runs.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories.offer_repo import OfferRepository
from app.services.offer_expiry_sweep import OfferExpirySweepService

pytestmark = pytest.mark.asyncio


async def _run_sweep() -> dict[str, int]:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = OfferExpirySweepService(offers=OfferRepository(session))
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"expired": result.expired}


def _seed_offer(
    db_engine: Engine,
    *,
    listing_id: UUID,
    buyer_id: UUID,
    status: str,
    expires_sql: str,
) -> UUID:
    offer_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO offers (id, listing_id, buyer_id, offered_price_kobo, status, "
                f"expires_at) VALUES (:id, :lid, :bid, 4000000000, :status, {expires_sql})"
            ),
            {"id": offer_id, "lid": listing_id, "bid": buyer_id, "status": status},
        )
    return offer_id


def _status(db_engine: Engine, offer_id: UUID) -> str:
    with db_engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT status FROM offers WHERE id = :id"), {"id": offer_id}
            ).scalar_one()
        )


async def test_expires_only_lapsed_live_offers(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)

    lapsed_pending = _seed_offer(
        db_engine,
        listing_id=listing,
        buyer_id=buyer,
        status="pending",
        expires_sql="NOW() - INTERVAL '1 hour'",
    )
    lapsed_countered = _seed_offer(
        db_engine,
        listing_id=listing,
        buyer_id=buyer,
        status="countered",
        expires_sql="NOW() - INTERVAL '2 hours'",
    )
    live_pending = _seed_offer(
        db_engine,
        listing_id=listing,
        buyer_id=buyer,
        status="pending",
        expires_sql="NOW() + INTERVAL '10 hours'",
    )
    accepted = _seed_offer(
        db_engine,
        listing_id=listing,
        buyer_id=buyer,
        status="accepted",
        expires_sql="NOW() - INTERVAL '5 hours'",
    )

    result = await _run_sweep()
    assert result == {"expired": 2}

    assert _status(db_engine, lapsed_pending) == "expired"
    assert _status(db_engine, lapsed_countered) == "expired"
    assert _status(db_engine, live_pending) == "pending"  # not past its window
    assert _status(db_engine, accepted) == "accepted"  # terminal — never expired


async def test_sweep_is_idempotent(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    _seed_offer(
        db_engine,
        listing_id=listing,
        buyer_id=buyer,
        status="pending",
        expires_sql="NOW() - INTERVAL '1 hour'",
    )

    first = await _run_sweep()
    second = await _run_sweep()

    assert first == {"expired": 1}
    assert second == {"expired": 0}  # already expired — excluded
