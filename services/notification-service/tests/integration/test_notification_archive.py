"""Integration tests for the notification archive sweep (SCRUM-120).

Seeds an old (>90d) and a recent notification, runs the sweep, and asserts the
old one is stamped archived_at while the recent one is untouched — and that an
archived row drops out of the in-app centre reads. Idempotent across runs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories.notification_repo import NotificationRepository
from app.services.notification_archive import NotificationArchiveService

pytestmark = pytest.mark.asyncio


async def _run_archive() -> dict[str, int]:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = NotificationArchiveService(
                notifications=NotificationRepository(session), retention_days=90
            )
            result = await service.run()
            await session.commit()
    finally:
        await engine.dispose()
    return {"archived": result.archived}


def _archived_at(db_engine: Engine, notif_id: UUID) -> object:
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT archived_at FROM notifications WHERE id = :id"), {"id": notif_id}
        ).scalar_one()


async def test_archives_old_leaves_recent(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
) -> None:
    user = seed_user()
    old = seed_notification(user_id=user, created_at=datetime.now(UTC) - timedelta(days=100))
    recent = seed_notification(user_id=user, created_at=datetime.now(UTC) - timedelta(days=10))

    result = await _run_archive()
    assert result == {"archived": 1}

    assert _archived_at(db_engine, old) is not None
    assert _archived_at(db_engine, recent) is None


async def test_archived_row_drops_out_of_the_centre(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
) -> None:
    user = seed_user()
    seed_notification(user_id=user, created_at=datetime.now(UTC) - timedelta(days=100))
    seed_notification(user_id=user, created_at=datetime.now(UTC) - timedelta(days=1))

    await _run_archive()

    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            repo = NotificationRepository(session)
            rows = await repo.list_for_user(user, limit=50)
            unread = await repo.unread_count(user)
    finally:
        await engine.dispose()

    # Only the recent (live) notification is visible in the centre.
    assert len(rows) == 1
    assert unread == 1


async def test_sweep_is_idempotent(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
) -> None:
    user = seed_user()
    seed_notification(user_id=user, created_at=datetime.now(UTC) - timedelta(days=200))

    first = await _run_archive()
    second = await _run_archive()

    assert first == {"archived": 1}
    assert second == {"archived": 0}  # already archived — excluded
