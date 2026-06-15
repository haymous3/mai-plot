"""Celery application for document-service background work.

CLAUDE.md non-negotiable: all background/async work goes through Celery
(broker + result backend on Redis), never asyncio.create_task() in a route.
The OCR pipeline (SCRUM-55) runs as an on-demand task triggered on document
upload — there is no beat schedule. Celery task failures are reported to
Sentry (review.md O8).
"""

from __future__ import annotations

import sentry_sdk
from celery import Celery
from sentry_sdk.integrations.celery import CeleryIntegration

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "document-service",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["app.tasks.document_ocr"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    timezone="UTC",
)

# Report Celery task failures to Sentry (review.md O8). No-op when SENTRY_DSN
# is unset, so local/CI runs are unaffected.
sentry_sdk.init(integrations=[CeleryIntegration()])
