"""Celery beat: proactively reopen lapsed 72h listing locks (SCRUM-149).

Thin wrapper around ListingLockSweepService — builds a fresh async session for
the worker and runs the (async) sweep inside asyncio.run(). No autoretry: the
sweep is idempotent (the repo query excludes already-cancelled deals), so a
transient failure is simply retried on the next beat.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.repositories.transaction_repo import TransactionRepository
from app.services.lock_sweep import ListingLockSweepService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = ListingLockSweepService(
                transactions=TransactionRepository(session),
                listings=ListingRepository(session),
                audit=AuditLogRepository(session),
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"scanned": result.scanned, "released": result.released}


@celery_app.task(name="app.tasks.lock_sweep.run_lock_sweep")  # type: ignore[untyped-decorator]
def run_lock_sweep() -> dict[str, int]:
    """Beat entry point — cancel abandoned offer_accepted deals + reopen listings."""
    return asyncio.run(_run())
