"""Beat-entry integration test for the lock sweep (SCRUM-149).

Exercises the Celery task wrapper itself (run_lock_sweep → asyncio.run(_run)),
which builds its own async engine against the test DB. Sync test (no asyncio
marker) so it can call the sync beat entry directly.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.tasks.lock_sweep import run_lock_sweep


def test_beat_entry_cancels_lapsed_lock(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing_id = seed_listing(seller_id=seller, status="under_offer")
    tx_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage, lock_expires_at) VALUES "
                "(:id, :lid, :bid, :sid, 5000000000, 'offer_accepted', NOW() - INTERVAL '1 hour')"
            ),
            {"id": tx_id, "lid": listing_id, "bid": buyer, "sid": seller},
        )

    result = run_lock_sweep()

    assert result == {"scanned": 1, "released": 1}
    with db_engine.connect() as conn:
        stage = conn.execute(
            text("SELECT stage FROM transactions WHERE id = :id"), {"id": tx_id}
        ).scalar_one()
        status = conn.execute(
            text("SELECT status FROM property_listings WHERE id = :id"), {"id": listing_id}
        ).scalar_one()
    assert stage == "cancelled"
    assert status == "active"
