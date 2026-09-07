"""Celery application for listing-service background work.

CLAUDE.md non-negotiable: all background/async work goes through Celery
(broker + result backend on Redis), never asyncio.create_task() in a route.
The beat schedule runs the listing-expiry job hourly. Celery task failures
are reported to Sentry (review.md O8).
"""

from __future__ import annotations

import sentry_sdk
from celery import Celery
from sentry_sdk.integrations.celery import CeleryIntegration

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "listing-service",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=[
        "app.tasks.listing_expiry",
        "app.tasks.listing_index",
        "app.tasks.view_count",
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
    task_default_queue="listing-service",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    timezone="UTC",
    beat_schedule={
        "expire-listings-hourly": {
            "task": "app.tasks.listing_expiry.run_listing_expiry",
            "schedule": _settings.expiry_beat_interval_seconds,
        },
    },
)

# Report Celery task failures to Sentry (review.md O8). No-op when SENTRY_DSN
# is unset, so local/CI runs are unaffected.
sentry_sdk.init(integrations=[CeleryIntegration()])
