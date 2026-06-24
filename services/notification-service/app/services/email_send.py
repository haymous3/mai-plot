"""Email send core (SCRUM-81) — sends one notification's email via SES.

The retryable unit, shared by the Celery task and the inline dispatcher. The
notification row already exists (dispatch wrote it); send loads it, resolves the
recipient's email, renders the template (with an NDPR unsubscribe link), sends
via SES, and stamps sent_at.

Terminal outcomes (missing row, already sent, no email on file) return without
raising. An SES failure raises EmailError so the Celery task retries with
backoff.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from uuid import UUID

from app.adapters.ses_email import EmailClient, EmailError
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.services.email_templates import render_email
from app.services.unsubscribe_token import make_unsubscribe_token

logger = logging.getLogger(__name__)


class EmailOutcome(StrEnum):
    SENT = "sent"
    ALREADY_SENT = "already_sent"
    NOT_FOUND = "not_found"
    NOT_EMAIL = "not_email"
    NO_EMAIL = "no_email"


class EmailSendService:
    def __init__(
        self,
        *,
        notifications: NotificationRepository,
        users: UserRepository,
        email_client: EmailClient,
        unsubscribe_base_url: str,
        unsubscribe_secret: str,
    ) -> None:
        self._notifications = notifications
        self._users = users
        self._email_client = email_client
        self._unsubscribe_base_url = unsubscribe_base_url
        self._unsubscribe_secret = unsubscribe_secret

    async def send(self, notification_id: UUID) -> EmailOutcome:
        notification = await self._notifications.get_by_id(notification_id)
        if notification is None:
            logger.warning("email.send.not_found", extra={"notification_id": str(notification_id)})
            return EmailOutcome.NOT_FOUND
        if notification.channel != "email":
            logger.warning(
                "email.send.not_email",
                extra={"notification_id": str(notification_id), "channel": notification.channel},
            )
            return EmailOutcome.NOT_EMAIL
        if notification.sent_at is not None:
            return EmailOutcome.ALREADY_SENT

        email = await self._users.get_email(notification.user_id)
        if not email:
            # No email on file — not retryable (a phone-only account has none).
            logger.info("email.send.no_email", extra={"notification_id": str(notification_id)})
            return EmailOutcome.NO_EMAIL

        token = make_unsubscribe_token(notification.user_id, secret=self._unsubscribe_secret)
        message = render_email(
            to=email,
            type=notification.type,
            title=notification.title,
            body=notification.body,
            unsubscribe_url=(
                f"{self._unsubscribe_base_url}?uid={notification.user_id}&token={token}"
            ),
        )

        try:
            await self._email_client.send(message)
        except EmailError:
            logger.warning("email.send.failed", extra={"notification_id": str(notification_id)})
            raise  # let the Celery task retry with backoff

        await self._notifications.mark_sent(notification_id)
        logger.info(
            "email.send.ok",
            extra={"notification_id": str(notification_id), "type": notification.type},
        )
        return EmailOutcome.SENT
