"""Integration tests for realtor commission disbursement (SCRUM-86) — real DB.

Seeds a funded escrow (a credit) for a transaction, then runs the disbursement
and asserts the real money effects: a payment_event walks to 'completed', an
escrow debit is recorded, and the balance drops. The Paystack transfer + receipt
are faked.
"""

from __future__ import annotations

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
from app.repositories.payout_account_repo import PayoutAccountRepository
from app.services.disbursement import (
    CommissionDisbursementService,
    DisburseOutcome,
    DisburseRequest,
)
from app.services.escrow_ledger import EscrowLedgerService

pytestmark = pytest.mark.asyncio

# Must match config default disbursement_actor_id.
_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _disburse(req: DisburseRequest) -> DisburseOutcome:
    """Run the disbursement once against the test DB (the Celery task's logic)."""
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = CommissionDisbursementService(
                payments=PaymentEventRepository(session),
                escrow=EscrowLedgerService(
                    ledger=EscrowLedgerRepository(session), audit=AuditLogRepository(session)
                ),
                receipts=InMemoryReceiptStorage(),
                transfer_client=FakePaystackTransferClient(),
                payout_accounts=PayoutAccountRepository(session),
                audit=AuditLogRepository(session),
                actor_id=_ACTOR_ID,
            )
            result = await service.disburse(req)
            await session.commit()
    finally:
        await engine.dispose()
    return result.outcome


def _seed_user(conn: object, user_id: UUID, role: str) -> None:
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO users (id, role, verified_status, is_active) "
            "VALUES (:id, :role, 'id_verified', TRUE) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": user_id, "role": role},
    )


def _seed_payout_account(conn: object, user_id: UUID) -> None:
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO payout_accounts (user_id, account_number, bank_code, "
            "account_name, recipient_code) VALUES "
            "(:uid, '0123456789', '058', 'Payee', :rcp) ON CONFLICT (user_id) DO NOTHING"
        ),
        {"uid": user_id, "rcp": f"RCP_{str(user_id)[:8]}"},
    )


def _seed_deal(
    db_engine: Engine, *, fund_escrow_kobo: int | None, realtor_has_payout: bool = True
) -> tuple[UUID, UUID, UUID]:
    """Seed actor + buyer + seller + realtor + a completed transaction. Optionally
    fund its escrow with a credit and register the realtor's payout account.
    Returns (transaction_id, seller_id, realtor_id)."""
    tx_id, buyer, seller, realtor = uuid4(), uuid4(), uuid4(), uuid4()
    with db_engine.begin() as conn:
        _seed_user(conn, _ACTOR_ID, "admin")  # the disbursement system actor
        _seed_user(conn, buyer, "buyer")
        _seed_user(conn, seller, "seller")
        _seed_user(conn, realtor, "realtor")
        if realtor_has_payout:
            _seed_payout_account(conn, realtor)
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, 5000000000, 'completed')"
            ),
            {"id": tx_id, "lid": uuid4(), "bid": buyer, "sid": seller},
        )
        if fund_escrow_kobo is not None:
            pe_id = uuid4()
            conn.execute(
                text(
                    "INSERT INTO payment_events (id, idempotency_key, payer_id, transaction_id, "
                    "amount_kobo, payment_type, provider, status) VALUES "
                    "(:id, :ik, :payer, :tid, :amt, 'buyer_deposit', 'paystack', 'completed')"
                ),
                {"id": pe_id, "ik": uuid4(), "payer": buyer, "tid": tx_id, "amt": fund_escrow_kobo},
            )
            conn.execute(
                text(
                    "INSERT INTO escrow_ledger (transaction_id, entry_type, amount_kobo, "
                    "description, payment_event_id, requires_dual_approval) "
                    "VALUES (:tid, 'credit', :amt, 'buyer deposit', :peid, FALSE)"
                ),
                {"tid": tx_id, "amt": fund_escrow_kobo, "peid": pe_id},
            )
    return tx_id, seller, realtor


def _payment_event(db_engine: Engine, transaction_id: UUID) -> Any:
    with db_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, payment_type, payee_id, provider_reference FROM payment_events "
                "WHERE transaction_id = :tid AND payment_type = 'realtor_commission'"
            ),
            {"tid": transaction_id},
        ).first()


async def test_disburses_from_funded_escrow(clean_tables: None, db_engine: Engine) -> None:
    tx_id, seller, realtor = _seed_deal(db_engine, fund_escrow_kobo=5_000_000_000)
    req = DisburseRequest(
        commission_id=uuid4(),
        transaction_id=tx_id,
        realtor_id=realtor,
        seller_id=seller,
        amount_kobo=100_000_000,  # ₦1M commission
    )

    assert await _disburse(req) == DisburseOutcome.disbursed

    pe = _payment_event(db_engine, tx_id)
    assert pe is not None
    assert pe.status == "completed"
    assert pe.payee_id == realtor
    assert pe.provider_reference.startswith("FAKE-PSTK-")

    with db_engine.connect() as conn:
        debit = conn.execute(
            text(
                "SELECT amount_kobo FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type = 'debit'"
            ),
            {"tid": tx_id},
        ).first()
        assert debit is not None
        assert debit.amount_kobo == 100_000_000


async def test_unfunded_escrow_fails_without_moving_money(
    clean_tables: None, db_engine: Engine
) -> None:
    tx_id, seller, realtor = _seed_deal(db_engine, fund_escrow_kobo=None)  # empty escrow
    req = DisburseRequest(
        commission_id=uuid4(),
        transaction_id=tx_id,
        realtor_id=realtor,
        seller_id=seller,
        amount_kobo=100_000_000,
    )

    assert await _disburse(req) == DisburseOutcome.insufficient_escrow

    pe = _payment_event(db_engine, tx_id)
    assert pe is not None and pe.status == "failed"
    with db_engine.connect() as conn:
        debits = conn.execute(
            text(
                "SELECT COUNT(*) FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type='debit'"
            ),
            {"tid": tx_id},
        ).scalar_one()
        assert debits == 0


async def test_no_payout_account_waits_without_moving_money(
    clean_tables: None, db_engine: Engine
) -> None:
    # Escrow IS funded, but the realtor has no payout account -> the recipient
    # gate short-circuits before any debit; a later sweep retries once they add one.
    tx_id, seller, realtor = _seed_deal(
        db_engine, fund_escrow_kobo=5_000_000_000, realtor_has_payout=False
    )
    req = DisburseRequest(
        commission_id=uuid4(),
        transaction_id=tx_id,
        realtor_id=realtor,
        seller_id=seller,
        amount_kobo=100_000_000,
    )

    assert await _disburse(req) == DisburseOutcome.no_payout_account

    with db_engine.connect() as conn:
        debits = conn.execute(
            text(
                "SELECT COUNT(*) FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type='debit'"
            ),
            {"tid": tx_id},
        ).scalar_one()
        assert debits == 0  # nothing moved


async def test_disbursement_is_idempotent(clean_tables: None, db_engine: Engine) -> None:
    tx_id, seller, realtor = _seed_deal(db_engine, fund_escrow_kobo=5_000_000_000)
    req = DisburseRequest(
        commission_id=uuid4(),
        transaction_id=tx_id,
        realtor_id=realtor,
        seller_id=seller,
        amount_kobo=100_000_000,
    )

    assert await _disburse(req) == DisburseOutcome.disbursed
    assert await _disburse(req) == DisburseOutcome.already_disbursed  # re-run no-ops

    with db_engine.connect() as conn:
        debits = conn.execute(
            text(
                "SELECT COUNT(*) FROM escrow_ledger "
                "WHERE transaction_id = :tid AND entry_type='debit'"
            ),
            {"tid": tx_id},
        ).scalar_one()
        assert debits == 1  # exactly one debit, no double-pay
