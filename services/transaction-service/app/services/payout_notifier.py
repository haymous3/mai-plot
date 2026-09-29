"""Tell a payee their payout bank account was set or changed (SCRUM-223).

The alert that makes a hijacked session visible: if someone else redirected a
payout, the owner learns of it from this email, not from a missing payment.
So it is sent with `force=True` — past any email opt-out — and names only the
bank and the last four digits.

Producer side of notification-service's `notifications.dispatch`, like
SellerNotifier, and BEST-EFFORT for the same reason: the account is already
saved, and failing the request over the message would leave the person unsure
whether their change took.

  * CeleryPayoutNotifier — production.
  * NullPayoutNotifier — dev/CI/tests; no broker needed.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

PAYOUT_ACCOUNT_CHANGED = "payout_account_changed"


class PayoutNotifier(Protocol):
    async def account_changed(
        self, *, user_id: UUID, account_last4: str, first_time: bool
    ) -> None:  # pragma: no cover - protocol
        ...


class NullPayoutNotifier:
    async def account_changed(self, *, user_id: UUID, account_last4: str, first_time: bool) -> None:
        return None


def change_message(*, account_last4: str, first_time: bool) -> tuple[str, str]:
    """(title, body). Written for the reader who did NOT make the change."""
    verb = "added" if first_time else "changed"
    title = f"Your payout account was {verb}"
    body = (
        f"The bank account your Maihomme payouts go to was {verb} to one ending "
        f"{account_last4}. If this wasn't you, change your password now and "
        "contact Maihomme support before any payout is made."
    )
    return title, body


class CeleryPayoutNotifier:
    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    async def account_changed(self, *, user_id: UUID, account_last4: str, first_time: bool) -> None:
        title, body = change_message(account_last4=account_last4, first_time=first_time)
        try:
            self._app.send_task(
                "notifications.dispatch",
                # SCRUM-210: cross-service, so the destination queue is explicit.
                queue="notification-service",
                kwargs={
                    "user_id": str(user_id),
                    "type": PAYOUT_ACCOUNT_CHANGED,
                    "title": title,
                    "body": body,
                    # Email is the point: an in-app notice is read by whoever
                    # holds the session, which may be the person making the
                    # change. No SMS — it cannot reach Nigerian networks yet.
                    "channels": ["in_app", "email"],
                    "force": True,
                },
            )
        except Exception as exc:  # broker down — never fail the saved change
            logger.warning(
                "payout_account.notify_failed", extra={"user_id": str(user_id), "error": str(exc)}
            )


def build_payout_notifier(*, enabled: bool, broker_url: str) -> PayoutNotifier:
    if enabled:
        return CeleryPayoutNotifier(broker_url=broker_url)
    return NullPayoutNotifier()
