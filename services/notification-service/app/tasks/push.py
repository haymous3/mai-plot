"""Celery task: send one notification's Web Push to a user's devices (SCRUM-79).

Thin wrapper around PushSendService — builds a fresh async session + Web Push
client for the worker process and runs the (async) send inside asyncio.run().
The logic + tests live in app/services/push_send.py.

Retries only on WebPushError (a transient transport failure), with exponential
backoff. Terminal outcomes — missing row, already sent, no/all-expired
subscriptions — return normally and are not retried.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.web_push import WebPushError, build_web_push_client
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.notification_repo import NotificationRepository
from app.repositories.push_subscription_repo import PushSubscriptionRepository
from app.services.push_send import PushSendService

_settings = get_settings()


async def _run(notification_id: UUID) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    web_push = build_web_push_client(
        use_fake=settings.web_push_use_fake,
        vapid_private_key=settings.vapid_private_key,
        vapid_subject=settings.vapid_subject,
        ttl=settings.push_ttl_seconds,
    )
    try:
        async with sessionmaker() as session:
            service = PushSendService(
                notifications=NotificationRepository(session),
                subscriptions=PushSubscriptionRepository(session),
                web_push=web_push,
            )
            outcome = await service.send(notification_id)
            await session.commit()
    finally:
        await engine.dispose()
    return outcome.value


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.push.send_push_notification",
    autoretry_for=(WebPushError,),
    retry_backoff=True,
    retry_backoff_max=_settings.push_task_retry_backoff_max_seconds,
    retry_jitter=True,
    max_retries=_settings.push_task_max_retries,
)
def send_push_notification(notification_id: str) -> str:
    """Send one notification's Web Push. Retries with backoff on transient failure."""
    return asyncio.run(_run(UUID(notification_id)))
