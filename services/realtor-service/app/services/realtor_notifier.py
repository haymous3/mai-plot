"""Realtor decision notification (SCRUM-71).

When an admin approves / rejects / suspends a realtor, the realtor is told
(in-app + email + SMS). Delivery is owned by notification-service; this is the
producer side — it enqueues the `notifications.dispatch` Celery task on the
shared broker (CLAUDE.md §3: cross-service async via Celery, not a sync REST
call). Best-effort: a broker outage is logged, never raised, so it can never
roll back the committed decision.

Two impls: CeleryRealtorNotifier (production) and NullRealtorNotifier
(dev/CI/tests — a no-op, so no broker is needed).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

_APPROVED_BODY = (
    "Your realtor application has been approved. You can now receive inspection "
    "assignments on Maiplot."
)


def _decision_message(*, status: str, reason: str | None) -> tuple[str, str, str]:
    """Return (type, title, body) for an approve/reject/suspend decision."""
    if status == "approved":
        return "realtor_approved", "You're approved as a Maiplot realtor", _APPROVED_BODY
    if status == "suspended":
        return (
            "realtor_suspended",
            "Your Maiplot realtor account is suspended",
            f"Your realtor account has been suspended. Reason: {reason}.",
        )
    return (
        "realtor_rejected",
        "Update on your Maiplot realtor application",
        (
            "Your realtor application was not approved. "
            f"Reason: {reason}. You may re-submit corrected details."
        ),
    )


class RealtorNotifier(Protocol):
    async def decision(
        self, *, user_id: UUID, status: str, reason: str | None
    ) -> None:  # pragma: no cover - protocol
        ...


class NullRealtorNotifier:
    """No-op notifier — the default when notifications are disabled (no broker)."""

    async def decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        return None


class CeleryRealtorNotifier:
    """Enqueues `notifications.dispatch` on the shared broker, best-effort."""

    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    async def decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        type_, title, body = _decision_message(status=status, reason=reason)
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(user_id),
                    "type": type_,
                    "title": title,
                    "body": body,
                    "channels": ["in_app", "email", "sms"],
                    "reference_type": "realtor",
                    "reference_id": str(user_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the decision
            logger.warning(
                "realtor.notify_failed",
                extra={"user_id": str(user_id), "status": status, "error": str(exc)},
            )


def build_realtor_notifier(*, enabled: bool, broker_url: str) -> RealtorNotifier:
    if enabled:
        return CeleryRealtorNotifier(broker_url=broker_url)
    return NullRealtorNotifier()
