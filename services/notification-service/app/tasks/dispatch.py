"""Celery task: raise a notification from another service (SCRUM-117).

This is the cross-service seam. Other services (transaction / listing / auth)
enqueue `notifications.dispatch` on the shared broker with a recipient + message
+ channels; the notification worker creates the per-channel rows and enqueues
the channel sends. The task name is stable + decoupled from this module path so
producers don't depend on internal layout.

Idempotency note: this fans out to NEW rows each call, so producers should fire
it once per event (best-effort) — a retry of this task would duplicate the
notification, hence no autoretry here (the per-channel send tasks own delivery
retries).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.ses_email import build_email_client
from app.adapters.termii import build_termii_client
from app.adapters.web_push import build_web_push_client
from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.notification_repo import NotificationRepository
from app.repositories.push_subscription_repo import PushSubscriptionRepository
from app.repositories.user_repo import UserRepository
from app.services.dispatch_factory import build_dispatch_service
from app.services.notification_dispatch import CRITICAL_CHANNELS


async def _run(
    *,
    user_id: str,
    type: str,
    body: str,
    title: str | None,
    channels: list[str] | None,
    reference_type: str | None,
    reference_id: str | None,
) -> None:
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
    web_push = build_web_push_client(
        use_fake=settings.web_push_use_fake,
        vapid_private_key=settings.vapid_private_key,
        vapid_subject=settings.vapid_subject,
        ttl=settings.push_ttl_seconds,
    )
    email_client = build_email_client(
        use_fake=settings.ses_use_fake,
        from_email=settings.ses_from_email,
        region=settings.ses_region,
        endpoint_url=settings.ses_endpoint_url,
    )
    try:
        async with sessionmaker() as session:
            service = build_dispatch_service(
                settings=settings,
                notifications=NotificationRepository(session),
                users=UserRepository(session),
                subscriptions=PushSubscriptionRepository(session),
                termii=termii,
                web_push=web_push,
                email_client=email_client,
            )
            await service.dispatch(
                user_id=UUID(user_id),
                type=type,
                body=body,
                title=title,
                channels=set(channels) if channels else CRITICAL_CHANNELS,
                reference_type=reference_type,
                reference_id=UUID(reference_id) if reference_id else None,
            )
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="notifications.dispatch")  # type: ignore[untyped-decorator]
def dispatch_notification(
    *,
    user_id: str,
    type: str,
    body: str,
    title: str | None = None,
    channels: list[str] | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> None:
    """Create + fan out one notification. Channels default to the critical set
    (in-app + SMS + Web Push)."""
    asyncio.run(
        _run(
            user_id=user_id,
            type=type,
            body=body,
            title=title,
            channels=channels,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )
