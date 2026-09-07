"""Celery queue routing (SCRUM-210).

Every service used to publish to — and every worker consumed from — the single
default "celery" queue, while each Celery app knows only its OWN tasks. A worker
that grabbed somebody else's task logged "Received unregistered task" and dropped
it, so on staging (ten workers) a task reached its owner about one time in ten.
That is why an approved realtor never got their registration-number email.

Nothing tested the producers at all — they were only ever exercised through their
Null variants — which is precisely how it shipped. These pin the two halves:

  * this service's own queue, so its beat tasks reach its own worker;
  * the destination queue on every CROSS-service send, without which the message
    lands in the sender's queue where nothing can run it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.celery_app import celery_app
from app.services.disbursement_producer import CeleryDisbursementProducer
from app.services.inspection_notifier import CeleryInspectionNotifier
from app.services.realtor_notifier import CeleryRealtorNotifier

_BROKER = "memory://"


class _RecordingApp:
    """Stands in for the ad-hoc Celery client the producers build.

    They are constructed with a broker URL but never connect until a send, so
    swapping `_app` after construction records the publish without a broker.
    """

    def __init__(self) -> None:
        self.sends: list[tuple[str, str | None]] = []

    def send_task(self, name: str, **kwargs: object) -> None:
        queue = kwargs.get("queue")
        self.sends.append((name, queue if isinstance(queue, str) else None))


def test_this_services_tasks_run_on_its_own_queue() -> None:
    """Without this, the beat's commission/reassignment/disbursement sweeps land
    on the shared queue and are eaten by whichever worker grabs them first."""
    assert celery_app.conf.task_default_queue == "realtor-service"


@pytest.mark.asyncio
async def test_realtor_decision_goes_to_the_notification_queue() -> None:
    """The SCRUM-207 approval email. This is the exact message that went missing:
    it was published to the default queue and dropped by another service's
    worker."""
    notifier = CeleryRealtorNotifier(broker_url=_BROKER)
    recorder = _RecordingApp()
    notifier._app = recorder

    await notifier.decision(
        user_id=uuid4(), status="approved", reason=None, registration_number="MH-R-000123"
    )

    assert recorder.sends == [("notifications.dispatch", "notification-service")]


@pytest.mark.asyncio
async def test_report_decision_goes_to_the_notification_queue() -> None:
    notifier = CeleryRealtorNotifier(broker_url=_BROKER)
    recorder = _RecordingApp()
    notifier._app = recorder

    await notifier.report_decision(
        user_id=uuid4(), inspection_id=uuid4(), status="approved", note=None
    )

    assert recorder.sends == [("notifications.dispatch", "notification-service")]


@pytest.mark.asyncio
async def test_inspection_notifications_go_to_the_notification_queue() -> None:
    notifier = CeleryInspectionNotifier(broker_url=_BROKER)
    recorder = _RecordingApp()
    notifier._app = recorder

    await notifier.assigned(realtor_id=uuid4(), inspection_id=uuid4())
    await notifier.time_proposed(user_id=uuid4(), inspection_id=uuid4())

    assert recorder.sends == [
        ("notifications.dispatch", "notification-service"),
        ("notifications.dispatch", "notification-service"),
    ]


@pytest.mark.asyncio
async def test_disbursement_goes_to_the_transaction_queue() -> None:
    """MONEY moves in transaction-service, never here — so this one being eaten
    silently meant a realtor's commission was simply never paid out."""
    producer = CeleryDisbursementProducer(broker_url=_BROKER)
    recorder = _RecordingApp()
    producer._app = recorder

    await producer.request_disbursement(
        commission_id=uuid4(),
        transaction_id=uuid4(),
        realtor_id=uuid4(),
        seller_id=uuid4(),
        amount_kobo=500_000_00,
    )

    assert recorder.sends == [("payments.disburse_commission", "transaction-service")]
