"""Wiring for NotificationDispatchService (SCRUM-117).

Builds the dispatch service's send-service + dispatcher graph from a set of
already-constructed repos + channel clients. Factored out so both call sites
share one wiring:

  * the FastAPI dependency (request path) — passes process-singleton clients so
    httpx/boto3 connections are reused;
  * the `notifications.dispatch` Celery task (cross-service seam) — passes
    freshly-built clients for the worker process.

Channel transport (Celery vs inline) is read from settings per channel, so a
worker enqueues per-channel send tasks while local/CI run them inline.
"""

from __future__ import annotations

from app.adapters.ses_email import EmailClient
from app.adapters.termii import TermiiClient
from app.adapters.web_push import WebPushClient
from app.config import Settings
from app.repositories.notification_repo import NotificationRepository
from app.repositories.preference_repo import PreferenceRepository
from app.repositories.push_subscription_repo import PushSubscriptionRepository
from app.repositories.user_repo import UserRepository
from app.services.email_dispatch import build_email_dispatcher
from app.services.email_send import EmailSendService
from app.services.notification_dispatch import NotificationDispatchService
from app.services.push_dispatch import build_push_dispatcher
from app.services.push_send import PushSendService
from app.services.sms_dispatch import build_sms_dispatcher
from app.services.sms_send import SmsSendService


def build_dispatch_service(
    *,
    settings: Settings,
    notifications: NotificationRepository,
    users: UserRepository,
    subscriptions: PushSubscriptionRepository,
    preferences: PreferenceRepository,
    termii: TermiiClient,
    web_push: WebPushClient,
    email_client: EmailClient,
) -> NotificationDispatchService:
    sms_send = SmsSendService(notifications=notifications, users=users, termii=termii)
    sms = build_sms_dispatcher(via_celery=settings.sms_via_celery, send_service=sms_send)
    push_send = PushSendService(
        notifications=notifications, subscriptions=subscriptions, web_push=web_push
    )
    push = build_push_dispatcher(via_celery=settings.push_via_celery, send_service=push_send)
    email_send = EmailSendService(
        notifications=notifications,
        users=users,
        email_client=email_client,
        unsubscribe_base_url=settings.unsubscribe_base_url,
        unsubscribe_secret=settings.unsubscribe_secret,
    )
    email = build_email_dispatcher(via_celery=settings.email_via_celery, send_service=email_send)
    return NotificationDispatchService(
        notifications=notifications,
        preferences=preferences,
        sms=sms,
        push=push,
        email=email,
    )
