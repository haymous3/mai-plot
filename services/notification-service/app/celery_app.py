"""Celery application for notification-service background work.

CLAUDE.md non-negotiable: all background/async work goes through Celery
(broker + result backend on Redis), never asyncio.create_task() in a route.
SMS sends run as tasks so a Termii outage retries with backoff off the request
path. Celery task failures are reported to Sentry (review.md O8). The beat runs
the 90-day notification archive sweep (SCRUM-120); everything else is on-demand.
"""

from __future__ import annotations

import sentry_sdk
from celery import Celery
from sentry_sdk.integrations.celery import CeleryIntegration

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "notification-service",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=[
        "app.tasks.sms",
        "app.tasks.push",
        "app.tasks.email",
        "app.tasks.dispatch",
        "app.tasks.archive",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    timezone="UTC",
    beat_schedule={
        # Archive notifications older than the retention window (90 days).
        "archive-old-notifications": {
            "task": "app.tasks.archive.run_notification_archive",
            "schedule": _settings.notification_archive_beat_interval_seconds,
        },
    },
)

# Report Celery task failures to Sentry (review.md O8). No-op when SENTRY_DSN
# is unset, so local/CI runs are unaffected.
sentry_sdk.init(integrations=[CeleryIntegration()])
