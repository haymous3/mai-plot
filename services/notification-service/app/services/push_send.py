"""Web Push send core (SCRUM-79) — delivers one notification to a user's devices.

The retryable unit, shared by the Celery task and the inline dispatcher. The
notification row already exists (dispatch wrote it); send fans it out to every
active push subscription the user has:

  * A 404/410 subscription is dead — soft-delete it and move on (terminal for
    that device).
  * Any other failure is transient — counted, and if NOTHING was delivered the
    whole send raises WebPushError so the Celery task retries with backoff.
  * As long as at least one device received it, the notification is marked sent.

Terminal outcomes (missing row, already sent, no/again-no subscriptions) return
without raising. Every path logs a structured delivery-status line.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from uuid import UUID

from app.adapters.web_push import (
    PushSubscriptionInfo,
    WebPushClient,
    WebPushError,
    WebPushSubscriptionExpired,
)
from app.repositories.notification_repo import NotificationRepository
from app.repositories.push_subscription_repo import PushSubscriptionRepository

logger = logging.getLogger(__name__)


class PushOutcome(StrEnum):
    SENT = "sent"
    ALREADY_SENT = "already_sent"
    NOT_FOUND = "not_found"
    NOT_PUSH = "not_push"
    NO_SUBSCRIPTIONS = "no_subscriptions"
    ALL_EXPIRED = "all_expired"


class PushSendService:
    def __init__(
        self,
        *,
        notifications: NotificationRepository,
        subscriptions: PushSubscriptionRepository,
        web_push: WebPushClient,
    ) -> None:
        self._notifications = notifications
        self._subscriptions = subscriptions
        self._web_push = web_push

    async def send(self, notification_id: UUID) -> PushOutcome:
        notification = await self._notifications.get_by_id(notification_id)
        if notification is None:
            logger.warning("push.send.not_found", extra={"notification_id": str(notification_id)})
            return PushOutcome.NOT_FOUND
        if notification.channel != "push":
            logger.warning(
                "push.send.not_push",
                extra={"notification_id": str(notification_id), "channel": notification.channel},
            )
            return PushOutcome.NOT_PUSH
        if notification.sent_at is not None:
            return PushOutcome.ALREADY_SENT

        subscriptions = await self._subscriptions.list_active_for_user(notification.user_id)
        if not subscriptions:
            logger.info(
                "push.send.no_subscriptions", extra={"notification_id": str(notification_id)}
            )
            return PushOutcome.NO_SUBSCRIPTIONS

        payload = json.dumps(
            {
                "title": notification.title,
                "body": notification.body,
                "type": notification.type,
                "reference_type": notification.reference_type,
                "reference_id": (
                    str(notification.reference_id) if notification.reference_id else None
                ),
            }
        )

        delivered = 0
        expired = 0
        transient = 0
        for sub in subscriptions:
            info = PushSubscriptionInfo(endpoint=sub.endpoint, p256dh=sub.p256dh, auth=sub.auth)
            try:
                await self._web_push.send(info, payload)
                delivered += 1
            except WebPushSubscriptionExpired:
                await self._subscriptions.soft_delete(sub.id)
                expired += 1
            except WebPushError:
                transient += 1

        if delivered > 0:
            await self._notifications.mark_sent(notification_id)
            logger.info(
                "push.send.ok",
                extra={
                    "notification_id": str(notification_id),
                    "delivered": delivered,
                    "expired": expired,
                    "transient_failures": transient,
                },
            )
            return PushOutcome.SENT

        if transient > 0:
            # Nothing got through and at least one failure was transient — retry.
            logger.warning(
                "push.send.failed",
                extra={"notification_id": str(notification_id), "transient_failures": transient},
            )
            raise WebPushError(f"all {transient} push deliveries failed transiently")

        # Every subscription was dead; they're now soft-deleted. Nothing to retry.
        logger.info(
            "push.send.all_expired",
            extra={"notification_id": str(notification_id), "expired": expired},
        )
        return PushOutcome.ALL_EXPIRED
