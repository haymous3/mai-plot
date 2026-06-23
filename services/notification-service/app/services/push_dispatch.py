"""Web Push dispatch seam (SCRUM-79) — how a written push notification is sent.

Mirrors the SMS dispatcher. Dispatch creates the push notification row, then
calls `enqueue(notification_id)` to deliver it off the request path:

  * CeleryPushDispatcher — production. Hands the id to the
    `send_push_notification` Celery task (retry + backoff live there). Enqueue is
    best-effort: a broker hiccup is logged, never raised.
  * InlinePushDispatcher — local/CI. Runs the same PushSendService inline against
    the request session + the in-memory Web Push fake. A transient WebPushError
    is swallowed (best-effort); the row simply stays unsent.

`build_push_dispatcher` picks the transport from settings (`push_via_celery`).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from app.adapters.web_push import WebPushError
from app.services.push_send import PushSendService

logger = logging.getLogger(__name__)


class PushDispatcher(Protocol):
    async def enqueue(self, notification_id: UUID) -> None:  # pragma: no cover - protocol
        ...


class CeleryPushDispatcher:
    """Production transport — dispatch the send to a Celery worker."""

    async def enqueue(self, notification_id: UUID) -> None:
        try:
            from app.tasks.push import send_push_notification

            send_push_notification.delay(str(notification_id))
        except Exception as exc:  # broker down etc. — never fail the caller
            logger.warning(
                "push.enqueue_failed",
                extra={"notification_id": str(notification_id), "error": str(exc)},
            )


class InlinePushDispatcher:
    """Local/CI transport — run the send inline (best-effort), no broker."""

    def __init__(self, *, send_service: PushSendService) -> None:
        self._send_service = send_service

    async def enqueue(self, notification_id: UUID) -> None:
        try:
            await self._send_service.send(notification_id)
        except WebPushError:
            logger.warning(
                "push.inline_send_failed", extra={"notification_id": str(notification_id)}
            )


def build_push_dispatcher(*, via_celery: bool, send_service: PushSendService) -> PushDispatcher:
    if via_celery:
        return CeleryPushDispatcher()
    return InlinePushDispatcher(send_service=send_service)
