"""Celery task: sync one listing to Elasticsearch (SCRUM-54).

Thin wrapper around ListingIndexSync — builds a fresh async session + search
index for the worker process and runs the (async) sync inside asyncio.run().
The logic + tests live in app/services/listing_index_sync.py.

The task lets exceptions propagate so Celery's autoretry_for retries the sync
with exponential backoff (AC: "failed sync retried with exponential backoff").
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.search_index import build_search_index
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.listing_repo import ListingRepository
from app.services.listing_index_sync import ListingIndexSync

_settings = get_settings()


async def _run(listing_id: UUID) -> str:
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
            action = await ListingIndexSync(index=index, listings=listings).sync(listing_id)
            await session.commit()
    finally:
        await engine.dispose()
    return action


# Celery's .task decorator is untyped; the wrapped function's own signature is
# explicit, so silence mypy's untyped-decorator complaint just here.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.listing_index.sync_listing_index",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=_settings.index_task_retry_backoff_max_seconds,
    retry_jitter=True,
    max_retries=_settings.index_task_max_retries,
)
def sync_listing_index(listing_id: str) -> str:
    """Sync a single listing's search document. Retries with backoff on failure."""
    return asyncio.run(_run(UUID(listing_id)))
