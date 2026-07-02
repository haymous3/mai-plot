"""Celery task: poll the bank for delayed loan decisions (SCRUM-130).

Beat task `app.tasks.loan_poll.poll_pending_loan_status`. Builds a fresh async
session for the worker and runs LoanStatusPoller inside asyncio.run(). No-op when
loan_poll_enabled is false (dev/CI). No autoretry: the poll is idempotent and runs
again on the next beat tick.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.bank import build_bank_adapter_registry
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.loan_repo import LoanRepository
from app.services.loan_decision import LoanDecisionWebhookService
from app.services.loan_notifier import build_loan_notifier
from app.services.loan_status_poller import LoanStatusPoller
from app.services.tx_tasks import build_tx_task_producer


async def _run() -> str:
    settings = get_settings()
    if not settings.loan_poll_enabled:
        return "disabled"

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            loans = LoanRepository(session)
            decisions = LoanDecisionWebhookService(
                loans=loans,
                notifier=build_loan_notifier(
                    enabled=settings.notifications_enabled,
                    broker_url=settings.celery_broker_url,
                ),
                tx_tasks=build_tx_task_producer(
                    enabled=settings.tx_tasks_enabled, broker_url=settings.celery_broker_url
                ),
                secret=settings.bank_webhook_secret,
            )
            poller = LoanStatusPoller(
                loans=loans,
                registry=build_bank_adapter_registry(
                    enabled=settings.bank_adapter_enabled,
                    timeout=settings.bank_request_timeout_seconds,
                    retries=settings.bank_max_retries,
                    base_delay=settings.bank_retry_base_delay_seconds,
                ),
                decisions=decisions,
                stale_minutes=settings.loan_poll_stale_minutes,
                batch_limit=settings.loan_poll_batch_limit,
            )
            result = await poller.run()
            await session.commit()
    finally:
        await engine.dispose()
    return f"scanned={result.scanned} decided={result.decided} errors={result.errors}"


@celery_app.task(name="app.tasks.loan_poll.poll_pending_loan_status")  # type: ignore[untyped-decorator]
def poll_pending_loan_status() -> str:
    """Beat entry point — returns a one-line summary of the sweep."""
    return asyncio.run(_run())
