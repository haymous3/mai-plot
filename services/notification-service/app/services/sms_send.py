"""SMS send core (SCRUM-80) — performs one Termii delivery for a notification.

This is the retryable unit, shared by both transports: the Celery task
(`send_sms_notification`) and the inline dispatcher call `SmsSendService.send`
with a notification id. The notification row already exists (the dispatch wrote
it); send loads it, resolves + validates the recipient's phone, dials Termii,
and stamps sent_at on success.

Failure handling (AC: "SMS failures do not crash the notification service"):
  * Missing row / already sent / unknown phone / invalid number → a terminal
    outcome is returned, NOT raised. There is nothing to retry.
  * Termii transport failure → TermiiError is raised so the Celery task's
    autoretry backs off and tries again (the row stays sent_at = NULL).
Every path logs a structured delivery-status line (AC: "SMS delivery status
logged").
"""

from __future__ import annotations

import logging
from enum import StrEnum
from uuid import UUID

from app.adapters.termii import TermiiClient, TermiiError
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.services.phone import InvalidPhoneNumber, normalize_ng_msisdn

logger = logging.getLogger(__name__)


class SmsOutcome(StrEnum):
    SENT = "sent"
    ALREADY_SENT = "already_sent"
    NOT_FOUND = "not_found"
    NOT_SMS = "not_sms"
    INVALID_NUMBER = "invalid_number"


class SmsSendService:
    def __init__(
        self,
        *,
        notifications: NotificationRepository,
        users: UserRepository,
        termii: TermiiClient,
    ) -> None:
        self._notifications = notifications
        self._users = users
        self._termii = termii

    async def send(self, notification_id: UUID) -> SmsOutcome:
        notification = await self._notifications.get_by_id(notification_id)
        if notification is None:
            logger.warning("sms.send.not_found", extra={"notification_id": str(notification_id)})
            return SmsOutcome.NOT_FOUND
        if notification.channel != "sms":
            logger.warning(
                "sms.send.not_sms",
                extra={"notification_id": str(notification_id), "channel": notification.channel},
            )
            return SmsOutcome.NOT_SMS
        if notification.sent_at is not None:
            # Idempotent: a retry that races a prior success is a no-op.
            return SmsOutcome.ALREADY_SENT

        raw_phone = await self._users.get_phone(notification.user_id)
        try:
            phone = normalize_ng_msisdn(raw_phone)
        except InvalidPhoneNumber as exc:
            # Not retryable — a bad/absent number won't fix itself on retry.
            logger.warning(
                "sms.send.invalid_number",
                extra={"notification_id": str(notification_id), "error": str(exc)},
            )
            return SmsOutcome.INVALID_NUMBER

        try:
            await self._termii.send_sms(phone, notification.body)
        except TermiiError:
            logger.warning(
                "sms.send.failed",
                extra={"notification_id": str(notification_id), "phone_suffix": phone[-4:]},
            )
            raise  # let the Celery task retry with backoff

        await self._notifications.mark_sent(notification_id)
        logger.info(
            "sms.send.ok",
            extra={
                "notification_id": str(notification_id),
                "type": notification.type,
                "phone_suffix": phone[-4:],
            },
        )
        return SmsOutcome.SENT
