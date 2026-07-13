"""Celery task: disburse a realtor commission (SCRUM-86).

Public task name `payments.disburse_commission` — realtor-service enqueues it by
this stable name (cross-service producer, the notifications.dispatch pattern).
Thin wrapper around CommissionDisbursementService: builds a fresh async session
for the worker and runs the (async) disbursement inside asyncio.run().

No autoretry: the disbursement is idempotent (payment_events UNIQUE +
status guard), so a transient failure is simply retried on the next sweep.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.paystack import build_paystack_transfer_client
from app.adapters.receipt_storage import build_receipt_storage
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowLedgerRepository
from app.repositories.payment_repo import PaymentEventRepository
from app.repositories.payout_account_repo import PayoutAccountRepository
from app.services.disbursement import (
    CommissionDisbursementService,
    DisburseRequest,
)
from app.services.escrow_ledger import EscrowLedgerService


async def _run(req: DisburseRequest) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = CommissionDisbursementService(
                payments=PaymentEventRepository(session),
                escrow=EscrowLedgerService(
                    ledger=EscrowLedgerRepository(session),
                    audit=AuditLogRepository(session),
                ),
                receipts=build_receipt_storage(
                    use_fake=settings.receipts_storage_use_fake,
                    bucket=settings.receipts_s3_bucket,
                    region=settings.receipts_s3_region,
                    endpoint_url=settings.receipts_s3_endpoint_url,
                ),
                transfer_client=build_paystack_transfer_client(
                    enabled=settings.paystack_enabled,
                    secret_key=settings.paystack_secret_key,
                    base_url=settings.paystack_base_url,
                ),
                payout_accounts=PayoutAccountRepository(session),
                audit=AuditLogRepository(session),
                actor_id=UUID(settings.disbursement_actor_id),
            )
            result = await service.disburse(req)
            await session.commit()
    finally:
        await engine.dispose()
    return result.outcome.value


@celery_app.task(name="payments.disburse_commission")  # type: ignore[untyped-decorator]
def disburse_commission(
    *,
    commission_id: str,
    transaction_id: str,
    realtor_id: str,
    seller_id: str,
    amount_kobo: int,
) -> str:
    """Entry point realtor-service enqueues. Returns the disbursement outcome."""
    req = DisburseRequest(
        commission_id=UUID(commission_id),
        transaction_id=UUID(transaction_id),
        realtor_id=UUID(realtor_id),
        seller_id=UUID(seller_id),
        amount_kobo=amount_kobo,
    )
    return asyncio.run(_run(req))
