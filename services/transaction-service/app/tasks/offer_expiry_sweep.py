"""Celery beat: proactively expire lapsed offers (SCRUM-118).

Thin wrapper around OfferExpirySweepService — builds a fresh async session for
the worker and runs the (async) sweep inside asyncio.run(). No autoretry: the
sweep is idempotent (already-expired offers are excluded), so a transient failure
is simply retried on the next beat.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.offer_repo import OfferRepository
from app.services.offer_expiry_sweep import OfferExpirySweepService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = OfferExpirySweepService(offers=OfferRepository(session))
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"expired": result.expired}


@celery_app.task(name="app.tasks.offer_expiry_sweep.run_offer_expiry_sweep")  # type: ignore[untyped-decorator]
def run_offer_expiry_sweep() -> dict[str, int]:
    """Beat entry point — mark lapsed pending/countered offers as expired."""
    return asyncio.run(_run())
