"""Celery application for transaction-service background work (SCRUM-86).

CLAUDE.md non-negotiable: all background/async work goes through Celery. This
worker CONSUMES the cross-service `payments.disburse_commission` task that
realtor-service enqueues (the mirror of the notifications.dispatch seam) and runs
the commission disbursement. The beat also runs the seller-disbursement sweep
(SCRUM-85: settle platform fee + seller proceeds for deals 48h past completion).
Task failures are reported to Sentry (review.md O8).
"""

from __future__ import annotations

import sentry_sdk
from celery import Celery
from sentry_sdk.integrations.celery import CeleryIntegration

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "transaction-service",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=[
        "app.tasks.disbursement",
        "app.tasks.seller_disbursement",
        "app.tasks.loan_disbursement",
        "app.tasks.loan_stage",
        "app.tasks.payout_reconciliation",
        "app.tasks.lock_sweep",
        "app.tasks.offer_expiry_sweep",
    ],
)

celery_app.conf.update(
    # SCRUM-210: this service's OWN queue, and the fix for cross-service task
    # theft. Every service used to publish to — and every worker consumed from —
    # the single default "celery" queue, while each Celery app knows only its own
    # tasks. A worker that grabbed somebody else's task logged "Received
    # unregistered task" and DROPPED it, so with ten workers on staging a task
    # reached its owner about one time in ten. Proven in the Railway logs:
    # realtor-celery-worker ate notification-service's send_email_notification,
    # and notification-celery-worker ate loan-service's poll_pending_loan_status.
    #
    # Setting task_default_queue fixes both halves at once: publishes land here,
    # and a worker started WITHOUT -Q consumes exactly its task_default_queue —
    # which is why no compose/render/Railway start command had to change.
    #
    # ⚠️ A cross-service send_task MUST now name the destination queue
    # explicitly (queue="notification-service"), or it lands in the sender's own
    # queue where nothing can run it.
    task_default_queue="transaction-service",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    timezone="UTC",
    beat_schedule={
        # Settle platform fee + seller proceeds for deals 48h past completion.
        "disburse-seller-proceeds": {
            "task": "app.tasks.seller_disbursement.run_seller_disbursement",
            "schedule": _settings.seller_disbursement_beat_interval_seconds,
        },
        # Reverse the escrow debit of any payout whose Paystack transfer failed.
        "reconcile-failed-payouts": {
            "task": "app.tasks.payout_reconciliation.run_payout_reconciliation",
            "schedule": _settings.payout_reconciliation_beat_interval_seconds,
        },
        # Cancel abandoned offer_accepted deals past their 72h lock + reopen the listing.
        "sweep-lapsed-locks": {
            "task": "app.tasks.lock_sweep.run_lock_sweep",
            "schedule": _settings.lock_sweep_beat_interval_seconds,
        },
        # Stamp status='expired' on pending/countered offers past their 72h window.
        "sweep-lapsed-offers": {
            "task": "app.tasks.offer_expiry_sweep.run_offer_expiry_sweep",
            "schedule": _settings.offer_expiry_sweep_beat_interval_seconds,
        },
    },
)

# Report Celery task failures to Sentry (review.md O8). No-op when SENTRY_DSN is
# unset, so local/CI runs are unaffected.
sentry_sdk.init(integrations=[CeleryIntegration()])
