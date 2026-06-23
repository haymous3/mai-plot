"""SMS dispatch seam (SCRUM-80) — how a written SMS notification reaches Termii.

The dispatch path creates the sms notification row, then calls
`enqueue(notification_id)` to send it OFF the request path. Two transports share
one Protocol (mirrors listing-service's index/OCR dispatchers):

  * CelerySmsDispatcher — production. Hands the id to the `send_sms_notification`
    Celery task (retry + backoff live there). Enqueue is best-effort: a broker
    hiccup is logged, never raised, so it can't fail the caller — the row stays
    sent_at = NULL for a later reconcile.
  * InlineSmsDispatcher — local/CI. Runs the same SmsSendService inline against
    the request session + the in-memory Termii fake, so a send is exercised
    end-to-end without a broker. A Termii failure is swallowed (best-effort) —
    the row simply stays unsent, exactly as in production.

`build_sms_dispatcher` picks the transport from settings (`sms_via_celery`).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from app.adapters.termii import TermiiError
from app.services.sms_send import SmsSendService

logger = logging.getLogger(__name__)


class SmsDispatcher(Protocol):
    async def enqueue(self, notification_id: UUID) -> None:  # pragma: no cover - protocol
        ...


class CelerySmsDispatcher:
    """Production transport — dispatch the send to a Celery worker."""

    async def enqueue(self, notification_id: UUID) -> None:
        # Imported lazily so the request path (and tests) never import Celery
        # task wiring unless this transport is actually used.
        try:
            from app.tasks.sms import send_sms_notification

            send_sms_notification.delay(str(notification_id))
        except Exception as exc:  # broker down etc. — never fail the caller
            logger.warning(
                "sms.enqueue_failed",
                extra={"notification_id": str(notification_id), "error": str(exc)},
            )


class InlineSmsDispatcher:
    """Local/CI transport — run the send inline (best-effort), no broker."""

    def __init__(self, *, send_service: SmsSendService) -> None:
        self._send_service = send_service

    async def enqueue(self, notification_id: UUID) -> None:
        try:
            await self._send_service.send(notification_id)
        except TermiiError:
            # Mirrors production: a transport failure leaves the row unsent
            # rather than bubbling up into the caller.
            logger.warning(
                "sms.inline_send_failed", extra={"notification_id": str(notification_id)}
            )


def build_sms_dispatcher(*, via_celery: bool, send_service: SmsSendService) -> SmsDispatcher:
    if via_celery:
        return CelerySmsDispatcher()
    return InlineSmsDispatcher(send_service=send_service)
