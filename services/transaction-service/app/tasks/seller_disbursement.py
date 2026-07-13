"""Celery beat: settle seller proceeds for completed deals (SCRUM-85).

Thin wrapper around SellerDisbursementService — builds a fresh async session for
the worker and runs the (async) sweep inside asyncio.run(). No autoretry: the
sweep is idempotent (payment_events UNIQUE + status guards), so a transient
failure is retried next beat.
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
from app.repositories.transaction_repo import TransactionRepository
from app.services.escrow_ledger import EscrowLedgerService
from app.services.seller_disbursement import SellerDisbursementService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = SellerDisbursementService(
                transactions=TransactionRepository(session),
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
                hold_hours=settings.seller_disbursement_hold_hours,
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {
        "scanned": result.scanned,
        "disbursed": result.disbursed,
        "pending": result.pending,
        "waiting": result.waiting,
    }


@celery_app.task(name="app.tasks.seller_disbursement.run_seller_disbursement")  # type: ignore[untyped-decorator]
def run_seller_disbursement() -> dict[str, int]:
    """Beat entry point — settle platform fee + seller proceeds for eligible deals."""
    return asyncio.run(_run())
