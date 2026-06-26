"""Celery task: sweep available commissions for disbursement (SCRUM-86 PR-B).

Thin wrapper around DisbursementService — builds a fresh async session for the
worker and runs the (async) sweep inside asyncio.run(). The sweep enqueues the
transaction-service `payments.disburse_commission` task for unpaid commissions
and reconciles completed ones to 'withdrawn'.

No autoretry: the sweep is idempotent (mark_withdrawn is guarded; the disburse
task is itself idempotent), so a transient failure is retried next beat.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.commission_repo import CommissionRepository
from app.services.disbursement_producer import build_disbursement_producer
from app.services.disbursement_service import DisbursementService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = DisbursementService(
                commissions=CommissionRepository(session),
                producer=build_disbursement_producer(
                    enabled=settings.disbursement_enabled,
                    broker_url=settings.celery_broker_url,
                ),
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {
        "scanned": result.scanned,
        "withdrawn": result.withdrawn,
        "requested": result.requested,
    }


@celery_app.task(name="app.tasks.disbursement.run_commission_disbursement")  # type: ignore[untyped-decorator]
def run_commission_disbursement() -> dict[str, int]:
    """Beat entry point — disburse available commissions + reconcile withdrawn."""
    return asyncio.run(_run())
