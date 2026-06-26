"""Integration tests for seller disbursement (SCRUM-85) — real DB.

Seeds a funded, completed deal whose 48h hold has elapsed, runs the sweep, and
asserts the real money effects: a platform_fee debit + a seller_disbursement
debit (net), completed payment_events, and the escrow drained to the reserved
realtor commission (0 when no realtor).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.paystack import FakePaystackTransferClient
from app.adapters.receipt_storage import InMemoryReceiptStorage
from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowLedgerRepository
from app.repositories.payment_repo import PaymentEventRepository
from app.repositories.transaction_repo import TransactionRepository
from app.services.escrow_ledger import EscrowLedgerService
from app.services.seller_disbursement import SellerDisbursementService

pytestmark = pytest.mark.asyncio

_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")
# Kept under the ₦10M dual-approval threshold so the seller debit settles directly.
_PRICE = 800_000_000
_FEE = 20_000_000


async def _run_sweep() -> Any:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = SellerDisbursementService(
                transactions=TransactionRepository(session),
                payments=PaymentEventRepository(session),
                escrow=EscrowLedgerService(
                    ledger=EscrowLedgerRepository(session), audit=AuditLogRepository(session)
                ),
                receipts=InMemoryReceiptStorage(),
                transfer_client=FakePaystackTransferClient(),
                audit=AuditLogRepository(session),
                actor_id=_ACTOR_ID,
                hold_hours=48,
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return result


def _user(conn: object, uid: UUID, role: str) -> None:
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO users (id, role, verified_status, is_active) "
            "VALUES (:id, :role, 'id_verified', TRUE) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": uid, "role": role},
    )


def _seed_completed_deal(db_engine: Engine, *, completed_hours_ago: int = 49) -> tuple[UUID, UUID]:
    """A funded, completed deal that reached 'completed' completed_hours_ago."""
    tx_id, buyer, seller = uuid4(), uuid4(), uuid4()
    completed_at = datetime.now(UTC) - timedelta(hours=completed_hours_ago)
    with db_engine.begin() as conn:
        _user(conn, _ACTOR_ID, "admin")
        _user(conn, buyer, "buyer")
        _user(conn, seller, "seller")
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, platform_fee_kobo, stage) VALUES "
                "(:id, :lid, :bid, :sid, :price, :fee, 'completed')"
            ),
            {
                "id": tx_id,
                "lid": uuid4(),
                "bid": buyer,
                "sid": seller,
                "price": _PRICE,
                "fee": _FEE,
            },
        )
        conn.execute(
            text(
                "INSERT INTO transaction_events (transaction_id, event_type, from_stage, "
                "to_stage, created_at) VALUES "
                "(:tid, 'stage_change', 'title_held', 'completed', :at)"
            ),
            {"tid": tx_id, "at": completed_at},
        )
        # Fund escrow with the buyer deposit.
        pe_id = uuid4()
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
                "INSERT INTO escrow_ledger (transaction_id, entry_type, amount_kobo, "
                "description, payment_event_id, requires_dual_approval) "
                "VALUES (:tid, 'credit', :amt, 'buyer deposit', :peid, FALSE)"
            ),
            {"tid": tx_id, "amt": _PRICE, "peid": pe_id},
        )
    return tx_id, seller


def _seed_commission(db_engine: Engine, *, transaction_id: UUID, amount_kobo: int) -> None:
    """A completed inspection + an accrued commission for the deal (realtor-svc)."""
    realtor, inspection_id = uuid4(), uuid4()
    with db_engine.begin() as conn:
        _user(conn, realtor, "realtor")
        conn.execute(
            text(
                "INSERT INTO inspections (id, transaction_id, realtor_id, proposed_date, "
                "status, assignment_expires_at) VALUES (:id, :tid, :r, NOW(), 'completed', NOW())"
            ),
            {"id": inspection_id, "tid": transaction_id, "r": realtor},
        )
        conn.execute(
            text(
                "INSERT INTO commissions (realtor_id, transaction_id, inspection_id, "
                "amount_kobo, rate_bps, status, available_at) "
                "VALUES (:r, :tid, :insp, :amt, 200, 'pending', NOW())"
            ),
            {"r": realtor, "tid": transaction_id, "insp": inspection_id, "amt": amount_kobo},
        )


def _balance(db_engine: Engine, transaction_id: UUID) -> int:
    with db_engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN entry_type='credit' THEN amount_kobo "
                    "ELSE -amount_kobo END), 0) FROM escrow_ledger WHERE transaction_id = :tid"
                ),
                {"tid": transaction_id},
            ).scalar_one()
        )


def _pe(db_engine: Engine, transaction_id: UUID, payment_type: str) -> Any:
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, amount_kobo, payee_id FROM payment_events "
                "WHERE transaction_id = :tid AND payment_type = :t"
            ),
            {"tid": transaction_id, "t": payment_type},
        ).first()


async def test_settles_deal_without_realtor(clean_tables: None, db_engine: Engine) -> None:
    tx_id, seller = _seed_completed_deal(db_engine)

    result = await _run_sweep()
    assert result.disbursed == 1

    fee = _pe(db_engine, tx_id, "platform_fee")
    assert fee is not None and fee.status == "completed" and fee.amount_kobo == _FEE
    seller_pe = _pe(db_engine, tx_id, "seller_disbursement")
    assert seller_pe is not None and seller_pe.status == "completed"
    assert seller_pe.amount_kobo == _PRICE - _FEE  # no commission reserved
    assert seller_pe.payee_id == seller
    assert _balance(db_engine, tx_id) == 0  # escrow fully drained


async def test_reserves_realtor_commission(clean_tables: None, db_engine: Engine) -> None:
    tx_id, _seller = _seed_completed_deal(db_engine)
    commission = 100_000_000
    _seed_commission(db_engine, transaction_id=tx_id, amount_kobo=commission)

    result = await _run_sweep()
    assert result.disbursed == 1

    seller_pe = _pe(db_engine, tx_id, "seller_disbursement")
    assert seller_pe.amount_kobo == _PRICE - _FEE - commission
    # The commission stays in escrow (debited later by SCRUM-86).
    assert _balance(db_engine, tx_id) == commission


async def test_not_yet_48h_is_skipped(clean_tables: None, db_engine: Engine) -> None:
    tx_id, _seller = _seed_completed_deal(db_engine, completed_hours_ago=10)

    result = await _run_sweep()
    assert result.scanned == 0  # hold not elapsed
    assert _pe(db_engine, tx_id, "seller_disbursement") is None


async def test_settlement_is_idempotent(clean_tables: None, db_engine: Engine) -> None:
    tx_id, _seller = _seed_completed_deal(db_engine)

    first = await _run_sweep()
    second = await _run_sweep()
    assert first.disbursed == 1
    assert second.scanned == 0  # already settled — excluded from the next sweep

    with db_engine.connect() as conn:
        debits = conn.execute(
            text(
                "SELECT COUNT(*) FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type = 'debit'"
            ),
            {"tid": tx_id},
        ).scalar_one()
        assert debits == 2  # platform_fee + seller, once each
