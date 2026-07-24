"""Integration tests for the lapsed 72h listing-lock sweep (SCRUM-149).

Seeds a deal parked at 'offer_accepted' whose lock window has passed (and the
listing is under_offer), runs the sweep, and asserts the real effect: the deal
is cancelled, the listing reopens to 'active', and the cancellation is recorded
in transaction_events + audit_log. A deal whose lock is still live is untouched,
and the sweep is idempotent.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.transaction_repo import TransactionRepository
from app.services.lock_sweep import ListingLockSweepService

pytestmark = pytest.mark.asyncio


async def _run_sweep() -> dict[str, int]:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = ListingLockSweepService(
                transactions=TransactionRepository(session),
                listings=ListingRepository(session),
                audit=AuditLogRepository(session),
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"scanned": result.scanned, "released": result.released}


def _seed_locked_deal(
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    *,
    lock_sql: str,
    stage: str = "offer_accepted",
) -> tuple[UUID, UUID]:
    """A deal at `stage` holding a listing's lock, with lock_expires_at set by
    `lock_sql` (a NOW()±interval expression). Returns (transaction_id, listing_id)."""
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing_id = seed_listing(seller_id=seller, status="under_offer")
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage, lock_expires_at) "
                f"VALUES (:id, :lid, :bid, :sid, :amt, :stage, {lock_sql})"
            ),
            {
                "id": tx_id,
                "lid": listing_id,
                "bid": buyer,
                "sid": seller,
                "amt": 5_000_000_000,
                "stage": stage,
            },
        )
    return tx_id, listing_id


def _stage(db_engine: Engine, tx_id: UUID) -> str:
    with db_engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT stage FROM transactions WHERE id = :id"), {"id": tx_id}
            ).scalar_one()
        )


def _listing_status(db_engine: Engine, listing_id: UUID) -> str:
    with db_engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
            ).scalar_one()
        )


async def test_sweeps_lapsed_lock_and_reopens_listing(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    tx_id, listing_id = _seed_locked_deal(
        db_engine, seed_user, seed_listing, lock_sql="NOW() - INTERVAL '1 hour'"
    )

    result = await _run_sweep()
    assert result == {"scanned": 1, "released": 1}

    assert _stage(db_engine, tx_id) == "cancelled"
    assert _listing_status(db_engine, listing_id) == "active"
    with db_engine.connect() as conn:
        events = conn.execute(
            text(
                "SELECT COUNT(*) FROM transaction_events "
                "WHERE transaction_id = :id AND event_type = 'lock_expired'"
            ),
            {"id": tx_id},
        ).scalar_one()
        assert events == 1
        audited = conn.execute(
            text(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE entity_id = :id AND action = 'transaction.cancelled'"
            ),
            {"id": tx_id},
        ).scalar_one()
        assert audited == 1


async def test_live_lock_is_left_untouched(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    tx_id, listing_id = _seed_locked_deal(
        db_engine, seed_user, seed_listing, lock_sql="NOW() + INTERVAL '10 hours'"
    )

    result = await _run_sweep()

    assert result == {"scanned": 0, "released": 0}
    assert _stage(db_engine, tx_id) == "offer_accepted"
    assert _listing_status(db_engine, listing_id) == "under_offer"


async def test_sweep_is_idempotent(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    _seed_locked_deal(db_engine, seed_user, seed_listing, lock_sql="NOW() - INTERVAL '1 hour'")

    first = await _run_sweep()
    second = await _run_sweep()

    assert first == {"scanned": 1, "released": 1}
    assert second == {"scanned": 0, "released": 0}  # cancelled deal no longer matches
