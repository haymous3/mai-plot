"""Listing expiry-warning notification (SCRUM-112).

48 hours before a listing expires, the seller is warned (Web Push primary, with
in-app + SMS) so they can renew or convert it to a normal sale. The send is
owned by notification-service; this is the producer side — it enqueues the
`notifications.dispatch` Celery task on the shared broker (CLAUDE.md §3:
cross-service async work goes via Celery). Best-effort: a broker outage is
logged, never raised, so it cannot break the expiry job.

Idempotency is handled upstream — `_warn_due` only processes a listing once per
expiry cycle (guarded by the `listing.expiry_warning` audit row), so the warning
is enqueued at most once per cycle.

Two impls: CeleryExpiryNotifier (production) and NullExpiryNotifier (dev/CI/tests
— a no-op, so no broker is needed).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

_TYPE = "listing_expiry_warning"
_TITLE = "Your listing is expiring soon"
_BODY = (
    "Your Maiplot listing expires within 48 hours. Renew it or convert it to a "
    "normal sale to keep it live."
)


class ExpiryNotifier(Protocol):
    async def expiry_warning(
        self, *, seller_id: UUID, listing_id: UUID
    ) -> None:  # pragma: no cover - protocol
        ...


class NullExpiryNotifier:
    """No-op notifier — the default when notifications are disabled (no broker)."""

    async def expiry_warning(self, *, seller_id: UUID, listing_id: UUID) -> None:
        return None


class CeleryExpiryNotifier:
    """Enqueues `notifications.dispatch` on the shared broker, best-effort."""

    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    async def expiry_warning(self, *, seller_id: UUID, listing_id: UUID) -> None:
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(seller_id),
                    "type": _TYPE,
                    "title": _TITLE,
                    "body": _BODY,
                    # Web Push primary + in-app + SMS fallback (CLAUDE.md).
                    "channels": ["in_app", "push", "sms"],
                    "reference_type": "listing",
                    "reference_id": str(listing_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the expiry job
            logger.warning(
                "listing.expiry_warning.notify_failed",
                extra={"listing_id": str(listing_id), "error": str(exc)},
            )


def build_expiry_notifier(*, enabled: bool, broker_url: str) -> ExpiryNotifier:
    if enabled:
        return CeleryExpiryNotifier(broker_url=broker_url)
    return NullExpiryNotifier()
