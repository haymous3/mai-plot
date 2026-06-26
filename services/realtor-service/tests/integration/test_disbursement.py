"""Integration tests for the commission disbursement sweep (SCRUM-86 PR-B).

Seeds an 'available' commission + its transaction; with no completed payout the
sweep leaves it available (and would enqueue), and once a completed
realtor_commission payment_event exists it reconciles the commission to
'withdrawn'. The producer is the no-op (disbursement_enabled=false).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories.commission_repo import CommissionRepository
from app.services.disbursement_producer import NullDisbursementProducer
from app.services.disbursement_service import DisbursementResult, DisbursementService

pytestmark = pytest.mark.asyncio


async def _run_sweep() -> DisbursementResult:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = DisbursementService(
                commissions=CommissionRepository(session),
                producer=NullDisbursementProducer(),
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return result


def _seed_available_commission(db_engine: Engine) -> tuple[UUID, UUID, UUID]:
    """Seed seller + realtor + a completed transaction + an 'available'
    commission. Returns (transaction_id, realtor_id, seller_id)."""
    tx_id, buyer, seller, realtor = uuid4(), uuid4(), uuid4(), uuid4()
    past = datetime.now(UTC)
    with db_engine.begin() as conn:
        # transactions.buyer_id/seller_id FK users — seed all parties first.
        for uid, role in ((buyer, "buyer"), (seller, "seller"), (realtor, "realtor")):
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": uid, "role": role},
            )
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, 5000000000, 'completed')"
            ),
            {"id": tx_id, "lid": uuid4(), "bid": buyer, "sid": seller},
        )
        conn.execute(
            text(
                "INSERT INTO commissions (realtor_id, transaction_id, inspection_id, "
                "amount_kobo, rate_bps, status, available_at) "
                "VALUES (:r, :tx, :insp, 100000000, 200, 'available', :at)"
            ),
            {"r": realtor, "tx": tx_id, "insp": uuid4(), "at": past},
        )
    return tx_id, realtor, seller


def _seed_completed_payout(db_engine: Engine, *, transaction_id: UUID, payer: UUID) -> UUID:
    pe_id = uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO payment_events (id, idempotency_key, payer_id, transaction_id, "
                "amount_kobo, payment_type, provider, status) VALUES "
                "(:id, :ik, :payer, :tid, 100000000, 'realtor_commission', 'paystack', 'completed')"
            ),
            {"id": pe_id, "ik": uuid4(), "payer": payer, "tid": transaction_id},
        )
    return pe_id


def _commission_row(db_engine: Engine, transaction_id: UUID) -> Any:
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, payment_event_id, disbursed_at FROM commissions "
                "WHERE transaction_id = :tid"
            ),
            {"tid": transaction_id},
        ).first()


async def test_available_without_payout_stays_available(
    clean_tables: None, db_engine: Engine
) -> None:
    tx_id, _realtor, _seller = _seed_available_commission(db_engine)

    result = await _run_sweep()

    assert result.requested >= 1  # this commission was (re-)enqueued
    row = _commission_row(db_engine, tx_id)
    assert row is not None and row.status == "available"  # not flipped yet


async def test_completed_payout_reconciles_to_withdrawn(
    clean_tables: None, db_engine: Engine
) -> None:
    tx_id, _realtor, seller = _seed_available_commission(db_engine)
    pe_id = _seed_completed_payout(db_engine, transaction_id=tx_id, payer=seller)

    result = await _run_sweep()

    assert result.withdrawn == 1
    row = _commission_row(db_engine, tx_id)
    assert row is not None
    assert row.status == "withdrawn"
    assert row.payment_event_id == pe_id
    assert row.disbursed_at is not None


async def test_reconcile_is_idempotent(clean_tables: None, db_engine: Engine) -> None:
    tx_id, _realtor, seller = _seed_available_commission(db_engine)
    _seed_completed_payout(db_engine, transaction_id=tx_id, payer=seller)

    first = await _run_sweep()
    second = await _run_sweep()

    assert first.withdrawn == 1
    assert second.withdrawn == 0  # already withdrawn — no double flip
