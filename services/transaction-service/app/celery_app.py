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
    ],
)

celery_app.conf.update(
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
    },
)

# Report Celery task failures to Sentry (review.md O8). No-op when SENTRY_DSN is
# unset, so local/CI runs are unaffected.
sentry_sdk.init(integrations=[CeleryIntegration()])
