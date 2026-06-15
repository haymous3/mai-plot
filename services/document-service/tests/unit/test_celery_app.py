"""Celery app wiring smoke test."""

from __future__ import annotations

# Importing the task module registers the task via @celery_app.task — exactly
# what the worker does for each entry in celery_app's `include` list.
import app.tasks.document_ocr  # noqa: F401  (import for registration side effect)
from app.celery_app import celery_app


def test_ocr_task_is_registered() -> None:
    assert "app.tasks.document_ocr.run_document_ocr" in celery_app.tasks


def test_broker_is_redis() -> None:
    assert str(celery_app.conf.broker_url).startswith("redis://")


def test_no_beat_schedule() -> None:
    # OCR is on-demand (triggered on upload), not scheduled.
    assert not celery_app.conf.beat_schedule
