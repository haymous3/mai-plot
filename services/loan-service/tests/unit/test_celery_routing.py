"""Celery queue routing (loan-service, SCRUM-210).

Every service used to publish to — and every worker consumed from — the single
default "celery" queue, while each Celery app knows only its OWN tasks. A worker
that grabbed somebody else's task logged "Received unregistered task" and dropped
it, so on staging (ten workers) a task reached its owner about one time in ten.
That is how an approved realtor's registration-number email went missing, and it
is why loan-service's own `poll_pending_loan_status` beat task turned up in the
NOTIFICATION worker's log as a KeyError.

Nothing tested these producers at all — they were only exercised through their
Null variants — which is precisely how it shipped.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.celery_app import celery_app
from app.services.loan_notifier import CeleryLoanNotifier
from app.services.tx_tasks import CeleryTxTaskProducer

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


def test_this_services_tasks_run_on_its_own_queue() -> None:
    """The loan status poll is the task the Railway logs caught landing in
    notification-celery-worker, which dropped it."""
    assert celery_app.conf.task_default_queue == "loan-service"


@pytest.mark.asyncio
async def test_loan_decision_goes_to_the_notification_queue() -> None:
    notifier = CeleryLoanNotifier(broker_url=_BROKER)
    recorder = _RecordingApp()
    notifier._app = recorder

    await notifier.loan_decision(
        buyer_id=uuid4(), loan_id=uuid4(), decision="approved", approved_amount_kobo=500_000_00
    )

    assert recorder.sends == [("notifications.dispatch", "notification-service")]


def test_transaction_tasks_go_to_the_transaction_queue() -> None:
    """Both are MONEY/state work owned by transaction-service. Eaten by the wrong
    worker, a disbursement credit simply never happened."""
    producer = CeleryTxTaskProducer(broker_url=_BROKER)
    recorder = _RecordingApp()
    producer._app = recorder

    producer.credit_loan_disbursement(
        loan_id=uuid4(), transaction_id=uuid4(), buyer_id=uuid4(), amount_kobo=500_000_00
    )
    producer.advance_loan_decision(transaction_id=uuid4(), decision="approved")

    assert recorder.sends == [
        ("payments.credit_loan_disbursement", "transaction-service"),
        ("transactions.advance_loan_decision", "transaction-service"),
    ]
