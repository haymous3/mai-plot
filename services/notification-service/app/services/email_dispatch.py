"""Email dispatch seam (SCRUM-81) — how a written email notification is sent.

Mirrors the SMS / push dispatchers. Dispatch creates the email notification row,
then calls `enqueue(notification_id)` to send it off the request path:

  * CeleryEmailDispatcher — production. Hands the id to the
    `send_email_notification` Celery task (retry + backoff live there). Enqueue
    is best-effort: a broker hiccup is logged, never raised.
  * InlineEmailDispatcher — local/CI. Runs the same EmailSendService inline
    against the request session + the in-memory SES fake. An EmailError is
    swallowed (best-effort); the row simply stays unsent.

`build_email_dispatcher` picks the transport from settings (`email_via_celery`).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from app.adapters.ses_email import EmailError
from app.services.email_send import EmailSendService

logger = logging.getLogger(__name__)


class EmailDispatcher(Protocol):
    async def enqueue(self, notification_id: UUID) -> None:  # pragma: no cover - protocol
        ...


class CeleryEmailDispatcher:
    """Production transport — dispatch the send to a Celery worker."""

    async def enqueue(self, notification_id: UUID) -> None:
        try:
            from app.tasks.email import send_email_notification

            send_email_notification.delay(str(notification_id))
        except Exception as exc:  # broker down etc. — never fail the caller
            logger.warning(
                "email.enqueue_failed",
                extra={"notification_id": str(notification_id), "error": str(exc)},
            )


class InlineEmailDispatcher:
    """Local/CI transport — run the send inline (best-effort), no broker."""

    def __init__(self, *, send_service: EmailSendService) -> None:
        self._send_service = send_service

    async def enqueue(self, notification_id: UUID) -> None:
        try:
            await self._send_service.send(notification_id)
        except EmailError:
            logger.warning(
                "email.inline_send_failed", extra={"notification_id": str(notification_id)}
            )


def build_email_dispatcher(*, via_celery: bool, send_service: EmailSendService) -> EmailDispatcher:
    if via_celery:
        return CeleryEmailDispatcher()
    return InlineEmailDispatcher(send_service=send_service)
