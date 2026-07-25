"""Celery beat: archive notifications older than the retention window (SCRUM-120).

Thin wrapper around NotificationArchiveService — builds a fresh async session for
the worker and runs the (async) sweep inside asyncio.run(). No autoretry: the
sweep is idempotent (already-archived rows are excluded), so a transient failure
is simply retried on the next beat.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.notification_repo import NotificationRepository
from app.services.notification_archive import NotificationArchiveService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = NotificationArchiveService(
                notifications=NotificationRepository(session),
                retention_days=settings.notification_retention_days,
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"archived": result.archived}


@celery_app.task(name="app.tasks.archive.run_notification_archive")  # type: ignore[untyped-decorator]
def run_notification_archive() -> dict[str, int]:
    """Beat entry point — archive notifications past the retention window."""
    return asyncio.run(_run())
