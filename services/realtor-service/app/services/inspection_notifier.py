"""Inspection assignment notification (SCRUM-72).

When a realtor is assigned an inspection, they're alerted with the 2-hour
acceptance window. Delivery is owned by notification-service; this enqueues the
`notifications.dispatch` Celery task on the shared broker (CLAUDE.md §3).
Best-effort: a broker outage is logged, never raised.

Two impls: CeleryInspectionNotifier (production) + NullInspectionNotifier
(dev/CI/tests).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Every date a realtor reads is a Nigerian local time. The rows are stored in
# UTC, so rendering them raw would tell a Lagos realtor to be at a property an
# hour before the buyer expects them.
_LAGOS = ZoneInfo("Africa/Lagos")

_ASSIGNED_LEAD = "You've been assigned a property inspection on Maihomme."
_ASSIGNED_TAIL = (
    "Accept it within 2 hours, or it will be offered to another realtor. "
    "Open your Maihomme dashboard to accept."
)
_RESCHEDULE_BODY = (
    "The realtor proposed a new time for your property inspection. Open Maihomme "
    "to see the updated schedule."
)


def format_inspection_datetime(value: datetime) -> str:
    """`Mon 15 Sep 2026, 10:00 AM WAT` — rendered in Lagos time, always."""
    local = value.astimezone(_LAGOS)
    # %-d / %-I are not portable to Windows; strip the zero by hand instead.
    day = str(int(local.strftime("%d")))
    hour = str(int(local.strftime("%I")))
    return f"{local:%a} {day} {local:%b %Y}, {hour}:{local:%M %p} WAT"


def build_assignment_body(
    *, property_title: str | None = None, proposed_date: datetime | None = None
) -> str:
    """Compose the assignment message from whatever the caller could supply.

    The property and date are optional because not every path has them — the
    sweep's row is built for proximity, not prose — and an assignment alert that
    is late is much worse than one that is vague. Whatever is present goes in a
    middle sentence, so the mail says WHERE and WHEN without the realtor having
    to log in to find out whether the job is even reachable for them.
    """
    parts = [_ASSIGNED_LEAD]
    if property_title and proposed_date is not None:
        parts.append(f"{property_title} on {format_inspection_datetime(proposed_date)}.")
    elif property_title:
        parts.append(f"{property_title}.")
    elif proposed_date is not None:
        parts.append(f"Scheduled for {format_inspection_datetime(proposed_date)}.")
    parts.append(_ASSIGNED_TAIL)
    return " ".join(parts)


class InspectionNotifier(Protocol):
    async def assigned(
        self,
        *,
        realtor_id: UUID,
        inspection_id: UUID,
        property_title: str | None = None,
        proposed_date: datetime | None = None,
    ) -> None:  # pragma: no cover - protocol
        ...

    async def time_proposed(
        self, *, user_id: UUID, inspection_id: UUID
    ) -> None:  # pragma: no cover - protocol
        ...


class NullInspectionNotifier:
    async def assigned(
        self,
        *,
        realtor_id: UUID,
        inspection_id: UUID,
        property_title: str | None = None,
        proposed_date: datetime | None = None,
    ) -> None:
        return None

    async def time_proposed(self, *, user_id: UUID, inspection_id: UUID) -> None:
        return None


class CeleryInspectionNotifier:
    def __init__(self, *, broker_url: str) -> None:
        from celery import Celery

        self._app = Celery(broker=broker_url)

    async def assigned(
        self,
        *,
        realtor_id: UUID,
        inspection_id: UUID,
        property_title: str | None = None,
        proposed_date: datetime | None = None,
    ) -> None:
        try:
            self._app.send_task(
                "notifications.dispatch",
                # SCRUM-210: cross-service, so the destination queue is explicit —
                # without it this lands in the sender's own queue and nothing runs it.
                queue="notification-service",
                kwargs={
                    "user_id": str(realtor_id),
                    "type": "inspection_assigned",
                    "title": "New inspection assignment",
                    "body": build_assignment_body(
                        property_title=property_title, proposed_date=proposed_date
                    ),
                    # SCRUM-213: EMAIL added. Before this an assignment went to
                    # in_app + push + sms — an in-app badge the realtor sees when
                    # they next log in, a browser push they most likely never
                    # granted, and an SMS that cannot reach a Nigerian network
                    # from the current sender at all (§2 / SCRUM-177). Email is
                    # the one channel that actually arrives, and the offer
                    # expires in 2 hours.
                    "channels": ["in_app", "push", "email", "sms"],
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
                # SCRUM-210: cross-service, so the destination queue is explicit —
                # without it this lands in the sender's own queue and nothing runs it.
                queue="notification-service",
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
