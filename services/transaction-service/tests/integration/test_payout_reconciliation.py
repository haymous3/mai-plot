"""Integration tests for the failed-payout escrow reversal sweep (SCRUM-147).

Seeds a funded deal whose payout debit is on the ledger but whose payment_event
is `failed` (the transfer.failed webhook, PR3), runs the sweep, and asserts the
real money effect: a compensating CREDIT is recorded against the payout's
payment_event and the escrow balance is restored — exactly once, even across two
runs. A payout still `processing` is left untouched.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowLedgerRepository
from app.services.escrow_ledger import EscrowLedgerService
from app.services.payout_reconciliation import PayoutReconciliationService

pytestmark = pytest.mark.asyncio

_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")
_FUNDING = 5_000_000_000  # ₦50M into escrow
_PAYOUT = 100_000_000  # ₦1M payout debit (under the ₦10M dual-approval threshold)


async def _run_sweep() -> dict[str, int]:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            ledger = EscrowLedgerRepository(session)
            service = PayoutReconciliationService(
                ledger=ledger,
                escrow=EscrowLedgerService(ledger=ledger, audit=AuditLogRepository(session)),
                actor_id=_ACTOR_ID,
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"scanned": result.scanned, "reversed": result.reversed}


def _seed_user(conn: object, user_id: UUID, role: str) -> None:
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO users (id, role, verified_status, is_active) "
            "VALUES (:id, :role, 'id_verified', TRUE) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": user_id, "role": role},
    )


def _seed_failed_payout(
    db_engine: Engine, *, payout_status: str = "failed", payment_type: str = "realtor_commission"
) -> tuple[UUID, UUID]:
    """A funded deal with a payout whose escrow debit is standing while the
    payout payment_event is `failed`. Returns (transaction_id, payout_pe_id)."""
    tx_id, buyer, seller, realtor = uuid4(), uuid4(), uuid4(), uuid4()
    deposit_pe, payout_pe = uuid4(), uuid4()
    with db_engine.begin() as conn:
        _seed_user(conn, _ACTOR_ID, "admin")
        _seed_user(conn, buyer, "buyer")
        _seed_user(conn, seller, "seller")
        _seed_user(conn, realtor, "realtor")
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, :amt, 'completed')"
            ),
            {"id": tx_id, "lid": uuid4(), "bid": buyer, "sid": seller, "amt": _FUNDING},
        )
        # Fund escrow: completed buyer deposit + credit entry.
        conn.execute(
            text(
                "INSERT INTO payment_events (id, idempotency_key, payer_id, transaction_id, "
                "amount_kobo, payment_type, provider, status) VALUES "
                "(:id, :ik, :payer, :tid, :amt, 'buyer_deposit', 'paystack', 'completed')"
            ),
            {"id": deposit_pe, "ik": uuid4(), "payer": buyer, "tid": tx_id, "amt": _FUNDING},
        )
        conn.execute(
            text(
                "INSERT INTO escrow_ledger (transaction_id, entry_type, amount_kobo, "
                "description, payment_event_id, requires_dual_approval) "
                "VALUES (:tid, 'credit', :amt, 'buyer deposit', :peid, FALSE)"
            ),
            {"tid": tx_id, "amt": _FUNDING, "peid": deposit_pe},
        )
        # The payout: a failed payment_event + a standing (effective) debit.
        conn.execute(
            text(
                "INSERT INTO payment_events (id, idempotency_key, payer_id, payee_id, "
                "transaction_id, amount_kobo, payment_type, provider, status) VALUES "
                "(:id, :ik, :payer, :payee, :tid, :amt, :ptype, 'paystack', :status)"
            ),
            {
                "id": payout_pe,
                "ik": uuid4(),
                "payer": seller,
                "payee": realtor,
                "tid": tx_id,
                "amt": _PAYOUT,
                "ptype": payment_type,
                "status": payout_status,
            },
        )
        conn.execute(
            text(
                "INSERT INTO escrow_ledger (transaction_id, entry_type, amount_kobo, "
                "description, payment_event_id, requires_dual_approval, approved_by_1) "
                "VALUES (:tid, 'debit', :amt, 'commission', :peid, FALSE, :actor)"
            ),
            {"tid": tx_id, "amt": _PAYOUT, "peid": payout_pe, "actor": _ACTOR_ID},
        )
    return tx_id, payout_pe


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


def _reversal_credits(db_engine: Engine, payout_pe: UUID) -> int:
    with db_engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM escrow_ledger "
                    "WHERE payment_event_id = :peid AND entry_type = 'credit'"
                ),
                {"peid": payout_pe},
            ).scalar_one()
        )


async def test_reverses_failed_payout_and_restores_balance(
    clean_tables: None, db_engine: Engine
) -> None:
    tx_id, payout_pe = _seed_failed_payout(db_engine)
    assert _balance(db_engine, tx_id) == _FUNDING - _PAYOUT  # debit standing

    result = await _run_sweep()
    assert result == {"scanned": 1, "reversed": 1}

    assert _balance(db_engine, tx_id) == _FUNDING  # debit undone
    assert _reversal_credits(db_engine, payout_pe) == 1
    with db_engine.connect() as conn:
        audited = conn.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE action = 'escrow.debit_reversed'"),
        ).scalar_one()
        assert audited == 1


async def test_sweep_is_idempotent(clean_tables: None, db_engine: Engine) -> None:
    tx_id, payout_pe = _seed_failed_payout(db_engine)

    first = await _run_sweep()
    second = await _run_sweep()

    assert first["reversed"] == 1
    assert second == {"scanned": 0, "reversed": 0}  # already reversed — excluded
    assert _reversal_credits(db_engine, payout_pe) == 1  # exactly one credit
    assert _balance(db_engine, tx_id) == _FUNDING


async def test_processing_payout_is_left_untouched(clean_tables: None, db_engine: Engine) -> None:
    tx_id, payout_pe = _seed_failed_payout(db_engine, payout_status="processing")

    result = await _run_sweep()

    assert result == {"scanned": 0, "reversed": 0}  # only failed payouts are swept
    assert _reversal_credits(db_engine, payout_pe) == 0
    assert _balance(db_engine, tx_id) == _FUNDING - _PAYOUT  # debit still standing
