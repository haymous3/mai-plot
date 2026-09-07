"""Celery queue routing (auth-service, SCRUM-210).

Every service used to publish to — and every worker consumed from — the single
default "celery" queue, while each Celery app knows only its OWN tasks. A worker
that grabbed somebody else's task logged "Received unregistered task" and dropped
it, so on staging (ten workers) a task reached its owner about one time in ten.
That is how an approved realtor's registration-number email went missing.

Nothing tested these producers at all — they were only exercised through their
Null variants — which is precisely how it shipped.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.poa_notifier import CeleryPoaNotifier

_BROKER = "memory://"


class _RecordingApp:
    """Stands in for the ad-hoc Celery client the producers build: constructed
    with a broker URL, but nothing connects until a send, so swapping `_app`
    records the publish without a broker."""

    def __init__(self) -> None:
        self.sends: list[tuple[str, str | None]] = []

    def send_task(self, name: str, **kwargs: object) -> None:
        queue = kwargs.get("queue")
        self.sends.append((name, queue if isinstance(queue, str) else None))


@pytest.mark.asyncio
async def test_poa_decision_goes_to_the_notification_queue() -> None:
    notifier = CeleryPoaNotifier(broker_url=_BROKER)
    recorder = _RecordingApp()
    notifier._app = recorder

    await notifier.poa_decision(user_id=uuid4(), status="approved", reason=None)

    assert recorder.sends == [("notifications.dispatch", "notification-service")]
