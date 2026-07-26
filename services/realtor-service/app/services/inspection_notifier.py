"""Inspection assignment notification (SCRUM-72).

When a realtor is auto-assigned an inspection, they're alerted with the 2-hour
acceptance window. Delivery is owned by notification-service; this enqueues the
`notifications.dispatch` Celery task on the shared broker (CLAUDE.md §3).
Best-effort: a broker outage is logged, never raised.

Two impls: CeleryInspectionNotifier (production) + NullInspectionNotifier
(dev/CI/tests).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

_BODY = (
    "You've been assigned a property inspection on Maiplot. Accept it within 2 "
    "hours, or it will be offered to another realtor."
)
_RESCHEDULE_BODY = (
    "The realtor proposed a new time for your property inspection. Open Maiplot "
    "to see the updated schedule."
)


class InspectionNotifier(Protocol):
    async def assigned(
        self, *, realtor_id: UUID, inspection_id: UUID
    ) -> None:  # pragma: no cover - protocol
        ...

    async def time_proposed(
        self, *, user_id: UUID, inspection_id: UUID
    ) -> None:  # pragma: no cover - protocol
        ...


class NullInspectionNotifier:
    async def assigned(self, *, realtor_id: UUID, inspection_id: UUID) -> None:
        return None

    async def time_proposed(self, *, user_id: UUID, inspection_id: UUID) -> None:
        return None


class CeleryInspectionNotifier:
    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    async def assigned(self, *, realtor_id: UUID, inspection_id: UUID) -> None:
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(realtor_id),
                    "type": "inspection_assigned",
                    "title": "New inspection assignment",
                    "body": _BODY,
                    # Time-sensitive (2h window) — in-app + push + SMS.
                    "channels": ["in_app", "push", "sms"],
                    "reference_type": "inspection",
                    "reference_id": str(inspection_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the assignment
            logger.warning(
                "inspection.notify_failed",
                extra={"inspection_id": str(inspection_id), "error": str(exc)},
            )

    async def time_proposed(self, *, user_id: UUID, inspection_id: UUID) -> None:
        try:
            self._app.send_task(
                "notifications.dispatch",
                kwargs={
                    "user_id": str(user_id),
                    "type": "inspection_rescheduled",
                    "title": "Inspection time changed",
                    "body": _RESCHEDULE_BODY,
                    "channels": ["in_app", "push"],
                    "reference_type": "inspection",
                    "reference_id": str(inspection_id),
                },
            )
        except Exception as exc:  # broker down etc. — never fail the reschedule
            logger.warning(
                "inspection.notify_failed",
                extra={"inspection_id": str(inspection_id), "error": str(exc)},
            )


def build_inspection_notifier(*, enabled: bool, broker_url: str) -> InspectionNotifier:
    if enabled:
        return CeleryInspectionNotifier(broker_url=broker_url)
    return NullInspectionNotifier()
