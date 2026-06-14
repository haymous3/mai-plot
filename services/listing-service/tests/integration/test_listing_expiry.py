"""Listing expiry job integration test (runs the service against Postgres)."""

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
from app.services.listing_expiry import ExpiryResult, ListingExpiryService


def _seed_expiring(db_engine: Engine, seller_id: UUID, *, interval: str) -> UUID:
    """Insert an active listing whose expires_at is NOW() + the given interval
    (e.g. '-1 hour' for already-expired, '24 hours' for within the warn window)."""
    listing_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO property_listings
                    (id, seller_id, property_type, title, address_text, location,
                     lga, state, asking_price_kobo, sale_type, status, expires_at)
                VALUES
                    (:id, :sid, 'land', 'Plot', '1 St',
                     ST_SetSRID(ST_MakePoint(3.4, 6.5), 4326)::geography,
                     'Ikeja', 'Lagos', 5000000000, 'normal', 'active',
                     NOW() + INTERVAL '{interval}')
                """
            ),
            {"id": listing_id, "sid": seller_id},
        )
    return listing_id


async def _run_expiry() -> ExpiryResult:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            listings = ListingRepository(session)
            service = ListingExpiryService(
                listings=listings,
                audit=AuditLogRepository(session),
                index_sync=None,  # index sync is covered by test_es_indexing
                warning_window_hours=48,
            )
            result = await service.run()
            await session.commit()
            return result
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expires_past_due_warns_soon_and_is_idempotent(
    clean_listing_tables: None,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
) -> None:
    seller = seed_seller(phone="08012345678")
    past = _seed_expiring(db_engine, seller, interval="-1 hour")
    future = _seed_expiring(db_engine, seller, interval="10 days")
    soon = _seed_expiring(db_engine, seller, interval="24 hours")

    result = await _run_expiry()
    assert result.expired == 1
    assert result.warned == 1

    with db_engine.connect() as conn:
        statuses = {
            r.id: r.status
            for r in conn.execute(text("SELECT id, status FROM property_listings")).all()
        }
        assert statuses[past] == "expired"
        assert statuses[future] == "active"
        assert statuses[soon] == "active"  # warned, not expired yet

        warned = {
            r.entity_id
            for r in conn.execute(
                text("SELECT entity_id FROM audit_log WHERE action = 'listing.expiry_warning'")
            ).all()
        }
        assert warned == {soon}

    # Idempotent: a second run expires nothing new and does not re-warn.
    again = await _run_expiry()
    assert again.expired == 0
    assert again.warned == 0
