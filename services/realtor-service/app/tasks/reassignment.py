"""Celery task: reassign lapsed inspection assignments (SCRUM-123).

Thin wrapper around ReassignmentService — builds a fresh async session for the
worker process and runs the (async) sweep inside asyncio.run(). The logic + tests
live in app/services/reassignment_service.py.

No autoretry: the sweep is idempotent (each reassign/defer is guarded on
status='pending') and the beat re-runs on its interval, so a transient failure is
simply retried next tick.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.inspection_repo import InspectionRepository
from app.repositories.realtor_repo import RealtorRepository
from app.services.inspection_notifier import build_inspection_notifier
from app.services.reassignment_service import ReassignmentService


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = ReassignmentService(
                inspections=InspectionRepository(session),
                realtors=RealtorRepository(session),
                notifier=build_inspection_notifier(
                    enabled=settings.notifications_enabled,
                    broker_url=settings.celery_broker_url,
                ),
                radius_meters=settings.inspection_radius_meters,
                window_hours=settings.inspection_window_hours,
                defer_hours=settings.reassignment_defer_hours,
                batch_limit=settings.reassignment_batch_limit,
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {
        "scanned": result.scanned,
        "reassigned": result.reassigned,
        "deferred": result.deferred,
    }


@celery_app.task(name="app.tasks.reassignment.run_inspection_reassignment")  # type: ignore[untyped-decorator]
def run_inspection_reassignment() -> dict[str, int]:
    """Beat entry point — reassign lapsed pending inspections to the next realtor."""
    return asyncio.run(_run())
