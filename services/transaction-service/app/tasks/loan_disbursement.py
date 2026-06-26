"""Celery task: credit escrow with a disbursed loan (SCRUM-128).

Public task name `payments.credit_loan_disbursement` — loan-service enqueues it by
this stable name on a `loan.disbursed` webhook (cross-service producer, the
notifications.dispatch / payments.disburse_commission pattern). Thin wrapper
around LoanDisbursementCreditService: builds a fresh async session for the worker
and runs the (async) credit inside asyncio.run().

No autoretry: the credit is idempotent (payment_events UNIQUE + a credit-exists
guard), so a transient failure is simply retried on the next webhook delivery.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowLedgerRepository
from app.repositories.payment_repo import PaymentEventRepository
from app.services.escrow_ledger import EscrowLedgerService
from app.services.loan_disbursement import CreditRequest, LoanDisbursementCreditService


async def _run(req: CreditRequest) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = LoanDisbursementCreditService(
                payments=PaymentEventRepository(session),
                escrow=EscrowLedgerService(
                    ledger=EscrowLedgerRepository(session),
                    audit=AuditLogRepository(session),
                ),
                audit=AuditLogRepository(session),
                actor_id=UUID(settings.disbursement_actor_id),
            )
            result = await service.credit(req)
            await session.commit()
    finally:
        await engine.dispose()
    return result.outcome.value


@celery_app.task(name="payments.credit_loan_disbursement")  # type: ignore[untyped-decorator]
def credit_loan_disbursement(
    *,
    loan_id: str,
    transaction_id: str,
    buyer_id: str,
    amount_kobo: int,
) -> str:
    """Entry point loan-service enqueues. Returns the credit outcome."""
    req = CreditRequest(
        loan_id=UUID(loan_id),
        transaction_id=UUID(transaction_id),
        buyer_id=UUID(buyer_id),
        amount_kobo=amount_kobo,
    )
    return asyncio.run(_run(req))
