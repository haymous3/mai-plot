"""Integration tests for the lapsed-inspection reassignment sweep (SCRUM-123).

Seeds a property + transaction + a pending inspection whose acceptance window has
already lapsed, then runs the sweep against the real DB and asserts the inspection
is handed to the next-nearest approved realtor (with the old one recorded in
declined_realtor_ids), or deferred when nobody else is in range.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories.inspection_repo import InspectionRepository
from app.repositories.realtor_repo import RealtorRepository
from app.services.inspection_notifier import NullInspectionNotifier
from app.services.reassignment_service import ReassignmentResult, ReassignmentService

pytestmark = pytest.mark.asyncio

# Property is at (lng=3.4, lat=6.5); +1.5 deg latitude is ~166 km (beyond 50 km).
_PROP_LNG, _PROP_LAT = 3.4, 6.5


async def _sweep() -> ReassignmentResult:
    """Run the reassignment sweep once against the test DB (the beat task's logic)."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = ReassignmentService(
                inspections=InspectionRepository(session),
                realtors=RealtorRepository(session),
                notifier=NullInspectionNotifier(),
                radius_meters=settings.inspection_radius_meters,
                window_hours=settings.inspection_window_hours,
                defer_hours=settings.reassignment_defer_hours,
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return result


def _seed_listing(conn: object, seller_id: UUID) -> UUID:
    listing_id = uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO property_listings
                (id, seller_id, property_type, title, address_text, location,
                 lga, state, asking_price_kobo, sale_type, status)
            VALUES
                (:id, :sid, 'land', 'Plot', '1 St',
                 ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                 'Ikeja', 'Lagos', 5000000000, 'normal', 'active')
            """
        ),
        {"id": listing_id, "sid": seller_id, "lng": _PROP_LNG, "lat": _PROP_LAT},
    )
    return listing_id


def _seed_transaction(conn: object, *, listing_id: UUID, buyer_id: UUID, seller_id: UUID) -> UUID:
    tx_id = uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, agreed_price_kobo) "
            "VALUES (:id, :lid, :bid, :sid, 5000000000)"
        ),
        {"id": tx_id, "lid": listing_id, "bid": buyer_id, "sid": seller_id},
    )
    return tx_id


def _seed_realtor(conn: object, *, lng: float, lat: float, approved: bool = True) -> UUID:
    user_id = uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO users (id, role, verified_status, is_active) "
            "VALUES (:id, 'realtor', 'id_verified', TRUE)"
        ),
        {"id": user_id},
    )
    conn.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO realtors
                (id, esvarbon_number, coverage_states, government_id_s3_key,
                 approval_status, base_location)
            VALUES
                (:id, :esv, ARRAY['Lagos'], 'realtor-id/x.pdf', :status,
                 ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography)
            """
        ),
        {
            "id": user_id,
            "esv": f"ESV/{uuid4().hex[:8].upper()}",
            "status": "approved" if approved else "pending",
            "lng": lng,
            "lat": lat,
        },
    )
    return user_id


def _seed_lapsed_inspection(conn: object, *, tx_id: UUID, realtor_id: UUID) -> UUID:
    """A pending inspection whose acceptance window expired an hour ago."""
    inspection_id = uuid4()
    proposed = datetime.now(UTC) + timedelta(days=1)
    expired = datetime.now(UTC) - timedelta(hours=1)
    conn.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO inspections
                (id, transaction_id, realtor_id, proposed_date, status, assignment_expires_at)
            VALUES (:id, :tx, :realtor, :proposed, 'pending', :expired)
            """
        ),
        {
            "id": inspection_id,
            "tx": tx_id,
            "realtor": realtor_id,
            "proposed": proposed,
            "expired": expired,
        },
    )
    return inspection_id


async def test_sweep_reassigns_to_next_nearest_and_records_decline(
    clean_tables: None, db_engine: Engine
) -> None:
    with db_engine.begin() as conn:
        buyer, seller = uuid4(), uuid4()
        for uid, role in ((buyer, "buyer"), (seller, "seller")):
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": uid, "role": role},
            )
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        # Both realtors at the property (~0 km, in range). `current` lapsed.
        current = _seed_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)
        backup = _seed_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)
        inspection_id = _seed_lapsed_inspection(conn, tx_id=tx_id, realtor_id=current)

    result = await _sweep()

    assert result.scanned == 1
    assert result.reassigned == 1
    assert result.deferred == 0

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT realtor_id, status, assignment_expires_at, declined_realtor_ids "
                "FROM inspections WHERE id = :id"
            ),
            {"id": inspection_id},
        ).first()
        assert row is not None
        assert row.realtor_id == backup
        assert row.status == "pending"
        assert current in list(row.declined_realtor_ids)  # old realtor recorded
        assert row.assignment_expires_at > datetime.now(UTC)  # window reset


async def test_sweep_defers_when_no_other_realtor_in_range(
    clean_tables: None, db_engine: Engine
) -> None:
    with db_engine.begin() as conn:
        buyer, seller = uuid4(), uuid4()
        for uid, role in ((buyer, "buyer"), (seller, "seller")):
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": uid, "role": role},
            )
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        current = _seed_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)  # only realtor in range
        inspection_id = _seed_lapsed_inspection(conn, tx_id=tx_id, realtor_id=current)

    result = await _sweep()

    assert result.reassigned == 0
    assert result.deferred == 1

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT realtor_id, status, assignment_expires_at FROM inspections WHERE id = :id"
            ),
            {"id": inspection_id},
        ).first()
        assert row is not None
        assert row.realtor_id == current  # unchanged — still theirs
        assert row.status == "pending"
        assert row.assignment_expires_at > datetime.now(UTC)  # window pushed out


async def test_sweep_ignores_non_lapsed_and_accepted(clean_tables: None, db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        buyer, seller = uuid4(), uuid4()
        for uid, role in ((buyer, "buyer"), (seller, "seller")):
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": uid, "role": role},
            )
        listing_id = _seed_listing(conn, seller)
        tx_id = _seed_transaction(conn, listing_id=listing_id, buyer_id=buyer, seller_id=seller)
        current = _seed_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)
        _seed_realtor(conn, lng=_PROP_LNG, lat=_PROP_LAT)  # a backup exists, but shouldn't be used
        # Pending but window still in the FUTURE -> not lapsed.
        future_id = uuid4()
        conn.execute(
            text(
                """
                INSERT INTO inspections
                    (id, transaction_id, realtor_id, proposed_date, status, assignment_expires_at)
                VALUES (:id, :tx, :realtor, NOW() + INTERVAL '1 day', 'pending',
                        NOW() + INTERVAL '1 hour')
                """
            ),
            {"id": future_id, "tx": tx_id, "realtor": current},
        )

    result = await _sweep()
    assert result == ReassignmentResult(scanned=0, reassigned=0, deferred=0)
