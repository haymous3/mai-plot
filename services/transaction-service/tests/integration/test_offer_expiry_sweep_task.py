"""Beat-entry integration test for the offer-expiry sweep (SCRUM-118).

Exercises the Celery task wrapper (run_offer_expiry_sweep → asyncio.run(_run)),
which builds its own async engine against the test DB. Sync test (no asyncio
marker) so it can call the sync beat entry directly.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.tasks.offer_expiry_sweep import run_offer_expiry_sweep


def test_beat_entry_expires_lapsed_offer(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    seller = seed_user(role="seller")
    listing = seed_listing(seller_id=seller)
    offer_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO offers (id, listing_id, buyer_id, offered_price_kobo, status, "
                "expires_at) VALUES (:id, :lid, :bid, 4000000000, 'pending', "
                "NOW() - INTERVAL '1 hour')"
            ),
            {"id": offer_id, "lid": listing, "bid": buyer},
        )

    result = run_offer_expiry_sweep()

    assert result == {"expired": 1}
    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM offers WHERE id = :id"), {"id": offer_id}
        ).scalar_one()
    assert status == "expired"
