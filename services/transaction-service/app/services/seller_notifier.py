"""Seller notification on a new offer (SCRUM-117).

When a buyer makes an offer, the seller is alerted so they can respond inside the
72h window. The notification itself is owned by notification-service; this is the
producer side — it enqueues the `notifications.dispatch` Celery task on the shared
broker (CLAUDE.md §3: cross-service async work goes via Celery, not a synchronous
REST call in the request path).

Sending is BEST-EFFORT: a broker outage is logged, never raised, so it can never
block or roll back the offer (the offer is the source of truth). Two impls:

  * CelerySellerNotifier — production. Fires the task by its stable public name.
  * NullSellerNotifier — dev/CI/tests. A no-op, so no broker is needed.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

_OFFER_RECEIVED = "offer_received"


class SellerNotifier(Protocol):
    async def offer_received(
        self, *, seller_id: UUID, offer_id: UUID, listing_id: UUID, amount_kobo: int
    ) -> None:  # pragma: no cover - protocol
        ...


class NullSellerNotifier:
    """No-op notifier — the default when notifications are disabled (no broker)."""

    async def offer_received(
        self, *, seller_id: UUID, offer_id: UUID, listing_id: UUID, amount_kobo: int
    ) -> None:
        return None


class CelerySellerNotifier:
    """Enqueues `notifications.dispatch` on the shared broker, best-effort."""

    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        # A producer-only Celery app: it publishes the message; the
        # notification-service worker (which registers the task) executes it.
        self._app = Celery(broker=broker_url)

    async def offer_received(
        self, *, seller_id: UUID, offer_id: UUID, listing_id: UUID, amount_kobo: int
    ) -> None:
        naira = amount_kobo // 100
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(seller_id),
                    "type": _OFFER_RECEIVED,
                    "title": "New offer on your listing",
                    "body": (
                        f"You've received a new offer of ₦{naira:,} on your listing. "
                        "Respond within 72 hours."
                    ),
                    "reference_type": "offer",
                    "reference_id": str(offer_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the offer
            logger.warning(
                "offer.notify_failed",
                extra={"offer_id": str(offer_id), "listing_id": str(listing_id), "error": str(exc)},
            )


def build_seller_notifier(*, enabled: bool, broker_url: str) -> SellerNotifier:
    if enabled:
        return CelerySellerNotifier(broker_url=broker_url)
    return NullSellerNotifier()
