"""Celery application for realtor-service background work (SCRUM-74).

CLAUDE.md non-negotiable: all background/async work goes through Celery (broker +
result backend on Redis). The beat schedule runs the commission-accrual job
hourly (record commissions for completed deals + release held ones) and the
inspection-reassignment sweep (SCRUM-123: hand lapsed pending inspections to the
next-nearest realtor), and the commission-disbursement sweep (SCRUM-86: enqueue
payouts for available commissions + reconcile completed ones to 'withdrawn').
Celery task failures are reported to Sentry (review.md O8).
"""

from __future__ import annotations

import sentry_sdk
from celery import Celery
from sentry_sdk.integrations.celery import CeleryIntegration

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "realtor-service",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["app.tasks.commission", "app.tasks.reassignment", "app.tasks.disbursement"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    timezone="UTC",
    beat_schedule={
        "accrue-commissions-hourly": {
            "task": "app.tasks.commission.run_commission_accrual",
            "schedule": _settings.commission_beat_interval_seconds,
        },
        "reassign-lapsed-inspections": {
            "task": "app.tasks.reassignment.run_inspection_reassignment",
            "schedule": _settings.reassignment_beat_interval_seconds,
        },
        "disburse-available-commissions": {
            "task": "app.tasks.disbursement.run_commission_disbursement",
            "schedule": _settings.disbursement_beat_interval_seconds,
        },
    },
)

# Report Celery task failures to Sentry (review.md O8). No-op when SENTRY_DSN is
# unset, so local/CI runs are unaffected.
sentry_sdk.init(integrations=[CeleryIntegration()])
