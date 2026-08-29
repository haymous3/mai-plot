"""Seller notifications: a new offer (SCRUM-117), a confirmed deposit (SCRUM-195).

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
_DEPOSIT_CONFIRMED = "deposit_confirmed"


class SellerNotifier(Protocol):
    async def offer_received(
        self, *, seller_id: UUID, offer_id: UUID, listing_id: UUID, amount_kobo: int
    ) -> None:  # pragma: no cover - protocol
        ...

    async def deposit_confirmed(
        self, *, seller_id: UUID, transaction_id: UUID, amount_kobo: int
    ) -> None:  # pragma: no cover - protocol
        ...


class NullSellerNotifier:
    """No-op notifier — the default when notifications are disabled (no broker)."""

    async def offer_received(
        self, *, seller_id: UUID, offer_id: UUID, listing_id: UUID, amount_kobo: int
    ) -> None:
        return None

    async def deposit_confirmed(
        self, *, seller_id: UUID, transaction_id: UUID, amount_kobo: int
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

    async def deposit_confirmed(
        self, *, seller_id: UUID, transaction_id: UUID, amount_kobo: int
    ) -> None:
        """Tell the seller a buyer's deposit has cleared into escrow.

        Fired from the Paystack webhook AFTER the escrow credit, and swallowed
        exactly like offer_received: the money has already moved and is the
        source of truth. Raising here would fail the webhook, Paystack would
        retry, and the retry path would have to re-derive that the credit
        already happened — risking noise on a ledger for the sake of a message.
        """
        naira = amount_kobo // 100
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(seller_id),
                    "type": _DEPOSIT_CONFIRMED,
                    "title": "Deposit confirmed",
                    "body": (
                        f"A deposit of ₦{naira:,} has been confirmed and credited "
                        "to the escrow account for your property."
                    ),
                    "reference_type": "transaction",
                    "reference_id": str(transaction_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the webhook
            logger.warning(
                "deposit.notify_failed",
                extra={"transaction_id": str(transaction_id), "error": str(exc)},
            )


def build_seller_notifier(*, enabled: bool, broker_url: str) -> SellerNotifier:
    if enabled:
        return CelerySellerNotifier(broker_url=broker_url)
    return NullSellerNotifier()
