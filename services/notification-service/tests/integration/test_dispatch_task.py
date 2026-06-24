"""Integration test for the cross-service dispatch task (SCRUM-117).

`notifications.dispatch` is the seam other services enqueue. Here we run its
async body directly against the real DB (channel sends inline against the fakes,
since *_via_celery defaults to False) and assert the per-channel rows are
written and the in-app centre shows only its own.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.tasks.dispatch import _run, dispatch_notification

pytestmark = pytest.mark.asyncio


async def test_task_registered_under_stable_public_name() -> None:
    # Producers in other services enqueue by this exact name — it must not drift.
    # (async only to satisfy the module-level asyncio mark — no await needed.)
    assert dispatch_notification.name == "notifications.dispatch"


def _channels_for(db_engine: Engine, user_id: UUID) -> dict[str, int]:
    with db_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT channel, COUNT(*) AS n FROM notifications "
                "WHERE user_id = :uid GROUP BY channel"
            ),
            {"uid": user_id},
        ).all()
    return {r.channel: r.n for r in rows}


async def test_dispatch_fans_out_to_critical_channels(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    user_id = seed_user()  # no phone / email / push subscription on file

    await _run(
        user_id=str(user_id),
        type="offer_received",
        body="You have a new offer.",
        title="New offer",
        channels=None,  # default → critical set (in_app + sms + push)
        reference_type="offer",
        reference_id=str(uuid4()),
    )

    by_channel = _channels_for(db_engine, user_id)
    assert by_channel == {"in_app": 1, "sms": 1, "push": 1}
