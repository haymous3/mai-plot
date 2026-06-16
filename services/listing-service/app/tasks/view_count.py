"""Celery task: increment a listing's view_count (SCRUM-114).

Thin wrapper — builds a fresh async session for the worker process and runs the
(async) increment inside asyncio.run(). On-demand (no beat), and intentionally
no autoretry: view_count is approximate analytics, so a missed bump on failure
is acceptable (the AC calls for best-effort, not exact-once).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.listing_repo import ListingRepository


async def _run(listing_id: UUID) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            await ListingRepository(session).increment_view_count(listing_id)
            await session.commit()
    finally:
        await engine.dispose()


# Celery's .task decorator is untyped; the wrapped function's own signature is
# explicit, so silence mypy's untyped-decorator complaint just here.
@celery_app.task(name="app.tasks.view_count.increment_view_count")  # type: ignore[untyped-decorator]
def increment_view_count(listing_id: str) -> None:
    """Increment one listing's view_count."""
    asyncio.run(_run(UUID(listing_id)))
