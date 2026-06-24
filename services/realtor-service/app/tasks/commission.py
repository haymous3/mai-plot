"""Celery task: accrue + release realtor commissions (SCRUM-74).

Thin wrapper around CommissionService — builds a fresh async session for the
worker process and runs the (async) accrual inside asyncio.run(). The logic +
tests live in app/services/commission_service.py.

No autoretry: accrual is idempotent (commissions are UNIQUE per transaction) and
the beat re-runs hourly, so a transient failure is simply retried next tick.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.commission_repo import CommissionRepository
from app.services.commission_service import CommissionService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = CommissionService(
                commissions=CommissionRepository(session),
                rate_bps=settings.commission_rate_bps,
                available_business_days=settings.commission_available_business_days,
            )
            result = await service.accrue()
            await session.commit()
    finally:
        await engine.dispose()
    return {"recorded": result.recorded, "released": result.released}


@celery_app.task(name="app.tasks.commission.run_commission_accrual")  # type: ignore[untyped-decorator]
def run_commission_accrual() -> dict[str, int]:
    """Beat entry point — accrue commissions for completed deals + release held."""
    return asyncio.run(_run())
