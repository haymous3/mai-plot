"""Beat-entry integration test for the notification archive sweep (SCRUM-120).

Exercises the Celery task wrapper (run_notification_archive → asyncio.run(_run)),
which builds its own async engine against the test DB. Sync test (no asyncio
marker) so it can call the sync beat entry directly.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.tasks.archive import run_notification_archive


def test_beat_entry_archives_old_notifications(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    seed_notification: Callable[..., UUID],
) -> None:
    user = seed_user()
    old = seed_notification(user_id=user, created_at=datetime.now(UTC) - timedelta(days=120))

    result = run_notification_archive()

    assert result == {"archived": 1}
    with db_engine.connect() as conn:
        archived_at = conn.execute(
            text("SELECT archived_at FROM notifications WHERE id = :id"), {"id": old}
        ).scalar_one()
    assert archived_at is not None
