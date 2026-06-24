"""Celery task: hourly listing expiry (SCRUM-53).

Thin wrapper around ListingExpiryService — builds a fresh async session +
search index for the worker process and runs the (async) job inside
asyncio.run(). The logic + tests live in app/services/listing_expiry.py.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.search_index import build_search_index
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.listing_repo import ListingRepository
from app.services.expiry_notifier import build_expiry_notifier
from app.services.listing_expiry import ListingExpiryService
from app.services.listing_index_sync import ListingIndexSync


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    index = build_search_index(
        use_fake=settings.search_use_fake,
        url=settings.elasticsearch_url,
        index=settings.es_listings_index,
    )
    try:
        async with sessionmaker() as session:
            listings = ListingRepository(session)
            service = ListingExpiryService(
                listings=listings,
                audit=AuditLogRepository(session),
                index_sync=ListingIndexSync(index=index, listings=listings),
                warning_window_hours=settings.expiry_warning_window_hours,
                notifier=build_expiry_notifier(
                    enabled=settings.notifications_enabled,
                    broker_url=settings.celery_broker_url,
                ),
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"expired": result.expired, "warned": result.warned}


# Celery's .task decorator is untyped; the wrapped function's own signature is
# explicit, so silence mypy's untyped-decorator complaint just here.
@celery_app.task(name="app.tasks.listing_expiry.run_listing_expiry")  # type: ignore[untyped-decorator]
def run_listing_expiry() -> dict[str, int]:
    """Beat entry point — runs the expiry + warning passes once."""
    return asyncio.run(_run())
