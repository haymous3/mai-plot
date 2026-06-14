"""Celery app wiring smoke test."""

from __future__ import annotations

# Importing the task module registers the task via @celery_app.task — exactly
# what the worker does for each entry in celery_app's `include` list.
import app.tasks.listing_expiry  # noqa: F401  (import for registration side effect)
from app.celery_app import celery_app


def test_expiry_task_is_registered() -> None:
    assert "app.tasks.listing_expiry.run_listing_expiry" in celery_app.tasks


def test_hourly_beat_schedule_present() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "expire-listings-hourly" in schedule
    entry = schedule["expire-listings-hourly"]
    assert entry["task"] == "app.tasks.listing_expiry.run_listing_expiry"
    assert entry["schedule"] == 3600.0


def test_broker_is_redis() -> None:
    assert str(celery_app.conf.broker_url).startswith("redis://")
