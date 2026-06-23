"""Celery task: send one notification's SMS via Termii (SCRUM-80).

Thin wrapper around SmsSendService — builds a fresh async session + Termii
client for the worker process and runs the (async) send inside asyncio.run().
The logic + tests live in app/services/sms_send.py.

The task retries only on TermiiError (a transient transport failure), with
exponential backoff (AC: "SMS failures do not crash the notification service
(silent retry)"). Terminal outcomes — missing row, already sent, unknown/invalid
number — return normally and are not retried.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.termii import TermiiError, build_termii_client
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.services.sms_send import SmsSendService

_settings = get_settings()


async def _run(notification_id: UUID) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    termii = build_termii_client(
        use_fake=settings.termii_use_fake,
        api_key=settings.termii_api_key,
        sender_id=settings.termii_sender_id,
        base_url=settings.termii_base_url,
        timeout_seconds=settings.termii_timeout_seconds,
    )
    try:
        async with sessionmaker() as session:
            service = SmsSendService(
                notifications=NotificationRepository(session),
                users=UserRepository(session),
                termii=termii,
            )
            outcome = await service.send(notification_id)
            await session.commit()
    finally:
        await engine.dispose()
    return outcome.value


# Celery's .task decorator is untyped; the wrapped function's own signature is
# explicit, so silence mypy's untyped-decorator complaint just here.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.sms.send_sms_notification",
    autoretry_for=(TermiiError,),
    retry_backoff=True,
    retry_backoff_max=_settings.sms_task_retry_backoff_max_seconds,
    retry_jitter=True,
    max_retries=_settings.sms_task_max_retries,
)
def send_sms_notification(notification_id: str) -> str:
    """Send one notification's SMS. Retries with backoff on Termii failure."""
    return asyncio.run(_run(UUID(notification_id)))
