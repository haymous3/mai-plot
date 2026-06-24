"""PoA decision notification (SCRUM-113).

When the legal team approves or rejects a Power-of-Attorney document, the seller
is told (in-app + SMS + email). Ownership of the actual delivery is
notification-service; this is the producer side — it enqueues the
`notifications.dispatch` Celery task on the shared broker (CLAUDE.md §3:
cross-service async work goes via Celery, not a synchronous REST call). This
replaces the inline Termii SMS that SCRUM-56 sent — both channels are now
orchestrated by notification-service from one decision event.

Sending is BEST-EFFORT: a broker outage is logged, never raised, so it can never
roll back the committed decision. Two impls:

  * CeleryPoaNotifier — production. Fires the task by its stable public name.
  * NullPoaNotifier — dev/CI/tests. A no-op, so no broker is needed.
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

_VERIFIED_BODY = "Your Power-of-Attorney document has been verified. You can now publish listings."


def _decision_message(*, status: str, reason: str | None) -> tuple[str, str, str]:
    """Return (type, title, body) for an approve/reject decision."""
    if status == "verified":
        return "poa_verified", "Power of Attorney verified", _VERIFIED_BODY
    return (
        "poa_rejected",
        "Power of Attorney not approved",
        (
            "Your Power-of-Attorney document was not approved. "
            f"Reason: {reason}. You may re-submit a corrected document."
        ),
    )


class PoaNotifier(Protocol):
    async def poa_decision(
        self, *, user_id: UUID, status: str, reason: str | None
    ) -> None:  # pragma: no cover - protocol
        ...


class NullPoaNotifier:
    """No-op notifier — the default when notifications are disabled (no broker)."""

    async def poa_decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        return None


class CeleryPoaNotifier:
    """Enqueues `notifications.dispatch` on the shared broker, best-effort."""

    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    async def poa_decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        type_, title, body = _decision_message(status=status, reason=reason)
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(user_id),
                    "type": type_,
                    "title": title,
                    "body": body,
                    "channels": ["in_app", "sms", "email"],
                    "reference_type": "user",
                    "reference_id": str(user_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the decision
            logger.warning(
                "poa.notify_failed",
                extra={"user_id": str(user_id), "status": status, "error": str(exc)},
            )


def build_poa_notifier(*, enabled: bool, broker_url: str) -> PoaNotifier:
    if enabled:
        return CeleryPoaNotifier(broker_url=broker_url)
    return NullPoaNotifier()
