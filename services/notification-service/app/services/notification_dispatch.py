"""Notification dispatch core (SCRUM-80).

The seam other services use to raise a notification. `dispatch` persists one row
per requested channel, then fans out the external sends off the request path:

  * in_app — written and immediately visible in the SCRUM-82 notification centre
    (sent_at stamped at insert, since "delivery" is just existing in the feed).
  * sms — written sent_at = NULL, then handed to the SMS dispatcher (Celery in
    prod, inline in dev/CI) which dials Termii and stamps sent_at on success.

`dispatch_critical_alert` is the common case for the deferred sends
(SCRUM-112/113/117): a critical event always reaches both the in-app centre AND
SMS, regardless of any future push/email preference (AC: "critical events
trigger SMS regardless of push preference"). Channel preferences belong to a
later ticket; nothing here consults them.

Commit ordering: with the Celery transport the SMS task is enqueued inside the
dispatch transaction, so the caller must commit promptly. If a worker picks the
task up before the row is visible the send is a no-op (logged NOT_FOUND), the
same best-effort/reconcile trade-off listing-service's index dispatcher makes.
An enqueue-after-commit hook (or a periodic reconcile of unsent sms rows) is a
follow-up to harden this once a caller wires it in.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

from app.repositories.notification_repo import NotificationRepository
from app.services.sms_dispatch import SmsDispatcher

IN_APP = "in_app"
SMS = "sms"
CRITICAL_CHANNELS: frozenset[str] = frozenset({IN_APP, SMS})


@dataclass(frozen=True)
class DispatchResult:
    """The rows written by one dispatch, by channel (None if not requested)."""

    in_app_id: UUID | None = None
    sms_id: UUID | None = None


class NotificationDispatchService:
    def __init__(
        self,
        *,
        notifications: NotificationRepository,
        sms: SmsDispatcher,
    ) -> None:
        self._notifications = notifications
        self._sms = sms

    async def dispatch(
        self,
        *,
        user_id: UUID,
        type: str,
        body: str,
        title: str | None = None,
        channels: Collection[str] = CRITICAL_CHANNELS,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
    ) -> DispatchResult:
        in_app_id: UUID | None = None
        sms_id: UUID | None = None

        if IN_APP in channels:
            row = await self._notifications.create(
                user_id=user_id,
                channel=IN_APP,
                type=type,
                title=title,
                body=body,
                reference_type=reference_type,
                reference_id=reference_id,
                sent_now=True,
            )
            in_app_id = row.id

        if SMS in channels:
            row = await self._notifications.create(
                user_id=user_id,
                channel=SMS,
                type=type,
                title=title,
                body=body,
                reference_type=reference_type,
                reference_id=reference_id,
                sent_now=False,
            )
            sms_id = row.id
            await self._sms.enqueue(sms_id)

        return DispatchResult(in_app_id=in_app_id, sms_id=sms_id)

    async def dispatch_critical_alert(
        self,
        *,
        user_id: UUID,
        type: str,
        body: str,
        title: str | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
    ) -> DispatchResult:
        """Raise a critical alert to both the in-app centre and SMS."""
        return await self.dispatch(
            user_id=user_id,
            type=type,
            body=body,
            title=title,
            channels=CRITICAL_CHANNELS,
            reference_type=reference_type,
            reference_id=reference_id,
        )
