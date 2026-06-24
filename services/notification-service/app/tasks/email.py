"""Celery task: send one notification's email via SES (SCRUM-81).

Thin wrapper around EmailSendService — builds a fresh async session + SES client
for the worker process and runs the (async) send inside asyncio.run(). The logic
+ tests live in app/services/email_send.py.

Retries only on EmailError (a transient SES failure), with exponential backoff.
Terminal outcomes — missing row, already sent, no email on file — return
normally and are not retried.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.ses_email import EmailError, build_email_client
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.services.email_send import EmailSendService

_settings = get_settings()


async def _run(notification_id: UUID) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    email_client = build_email_client(
        use_fake=settings.ses_use_fake,
        from_email=settings.ses_from_email,
        region=settings.ses_region,
        endpoint_url=settings.ses_endpoint_url,
    )
    try:
        async with sessionmaker() as session:
            service = EmailSendService(
                notifications=NotificationRepository(session),
                users=UserRepository(session),
                email_client=email_client,
                unsubscribe_base_url=settings.unsubscribe_base_url,
                unsubscribe_secret=settings.unsubscribe_secret,
            )
            outcome = await service.send(notification_id)
            await session.commit()
    finally:
        await engine.dispose()
    return outcome.value


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.email.send_email_notification",
    autoretry_for=(EmailError,),
    retry_backoff=True,
    retry_backoff_max=_settings.email_task_retry_backoff_max_seconds,
    retry_jitter=True,
    max_retries=_settings.email_task_max_retries,
)
def send_email_notification(notification_id: str) -> str:
    """Send one notification's email. Retries with backoff on SES failure."""
    return asyncio.run(_run(UUID(notification_id)))
