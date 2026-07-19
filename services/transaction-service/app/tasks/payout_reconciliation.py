"""Celery beat: reverse escrow debits of failed payouts (SCRUM-147).

Thin wrapper around PayoutReconciliationService — builds a fresh async session
for the worker and runs the (async) sweep inside asyncio.run(). No autoretry: the
sweep is idempotent (the repo query excludes already-reversed payouts), so a
transient failure is simply retried on the next beat.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.escrow_repo import EscrowLedgerRepository
from app.services.escrow_ledger import EscrowLedgerService
from app.services.payout_reconciliation import PayoutReconciliationService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            ledger = EscrowLedgerRepository(session)
            service = PayoutReconciliationService(
                ledger=ledger,
                escrow=EscrowLedgerService(ledger=ledger, audit=AuditLogRepository(session)),
                actor_id=UUID(settings.disbursement_actor_id),
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"scanned": result.scanned, "reversed": result.reversed}


@celery_app.task(name="app.tasks.payout_reconciliation.run_payout_reconciliation")  # type: ignore[untyped-decorator]
def run_payout_reconciliation() -> dict[str, int]:
    """Beat entry point — reverse the escrow debits of failed payouts."""
    return asyncio.run(_run())
