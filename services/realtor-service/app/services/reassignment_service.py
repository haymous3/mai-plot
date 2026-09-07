"""Reassign lapsed inspection assignments (SCRUM-123).

When a realtor doesn't accept an assigned inspection within the acceptance window
(`assignment_expires_at`), the inspection stays `pending` but stale. This sweep —
run by a Celery beat (app/tasks/reassignment.py) — finds those lapsed pending
inspections and hands each to the NEXT-nearest approved realtor, excluding anyone
who already declined/lapsed it (tracked in `declined_realtor_ids`).

When no other realtor is in range, the assignment is DEFERRED (the window is
pushed out) and an admin alert is logged, rather than left to be re-picked every
tick. The current realtor keeps the assignment until someone closer is available.

The same sweep also PLACES unassigned requests (SCRUM-208) — rows with no
realtor at all, created when a request found nobody in range. That makes the
dropped-request fallback self-healing: a realtor who becomes eligible picks up
the backlog on the next tick without an admin touching it. An unassigned row is
never "deferred" (there is no window to push out and no incumbent to keep); it
simply stays in the queue for the next pass, and for the admin.

Idempotent: each reassign/defer is guarded on status='pending', each placement on
status='unassigned', and the next beat re-processes anything still outstanding.
No money or state-machine changes here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.repositories.inspection_repo import LapsedInspection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReassignmentResult:
    scanned: int
    reassigned: int
    deferred: int
    # Unassigned requests the sweep managed to place (SCRUM-208). Counted apart
    # from `reassigned` because nothing was taken from anybody — this is work
    # that had no realtor at all finally reaching one.
    placed: int = 0


class _Inspections(Protocol):
    async def list_lapsed_pending(self, *, limit: int = 500) -> list[LapsedInspection]: ...

    async def list_unassigned_for_sweep(self, *, limit: int = 500) -> list[LapsedInspection]: ...

    async def place(
        self, inspection_id: UUID, *, realtor_id: UUID, window_hours: int
    ) -> object | None: ...

    async def reassign(
        self, inspection_id: UUID, *, old_realtor_id: UUID, new_realtor_id: UUID, window_hours: int
    ) -> bool: ...

    async def defer_assignment(self, inspection_id: UUID, *, hours: int) -> bool: ...


@dataclass(frozen=True)
class _PlacementCount:
    scanned: int
    placed: int


class _Realtors(Protocol):
    async def find_nearest_approved(
        self, *, listing_id: UUID, radius_m: float, exclude: list[UUID] | None = None
    ) -> UUID | None: ...


class _Notifier(Protocol):
    async def assigned(self, *, realtor_id: UUID, inspection_id: UUID) -> None: ...


class ReassignmentService:
    def __init__(
        self,
        *,
        inspections: _Inspections,
        realtors: _Realtors,
        notifier: _Notifier,
        radius_meters: float,
        window_hours: int,
        defer_hours: int,
        batch_limit: int = 500,
    ) -> None:
        self._inspections = inspections
        self._realtors = realtors
        self._notifier = notifier
        self._radius_meters = radius_meters
        self._window_hours = window_hours
        self._defer_hours = defer_hours
        self._batch_limit = batch_limit

    async def run(self) -> ReassignmentResult:
        placed = await self._place_unassigned()
        lapsed = await self._inspections.list_lapsed_pending(limit=self._batch_limit)
        reassigned = 0
        deferred = 0
        for item in lapsed:
            if item.realtor_id is None:
                # Unreachable: this list is status='pending' only, and the DB
                # CHECK (migration 0008) forbids a pending row without a realtor.
                # Skipped rather than asserted so a malformed row cannot stop the
                # whole sweep for every other inspection in the batch.
                logger.warning(
                    "inspection.lapsed_without_realtor",
                    extra={"inspection_id": str(item.inspection_id)},
                )
                continue
            # Never re-offer to the current assignee or anyone who already lapsed.
            exclude = [*item.declined_realtor_ids, item.realtor_id]
            next_realtor = await self._realtors.find_nearest_approved(
                listing_id=item.listing_id, radius_m=self._radius_meters, exclude=exclude
            )
            if next_realtor is None:
                if await self._inspections.defer_assignment(
                    item.inspection_id, hours=self._defer_hours
                ):
                    deferred += 1
                    logger.warning(
                        "inspection.reassignment_exhausted",
                        extra={
                            "inspection_id": str(item.inspection_id),
                            "listing_id": str(item.listing_id),
                            "deferred_hours": self._defer_hours,
                        },
                    )
                continue

            if await self._inspections.reassign(
                item.inspection_id,
                old_realtor_id=item.realtor_id,
                new_realtor_id=next_realtor,
                window_hours=self._window_hours,
            ):
                reassigned += 1
                # Best-effort alert; a broker outage must not undo the reassign.
                await self._notifier.assigned(
                    realtor_id=next_realtor, inspection_id=item.inspection_id
                )
        return ReassignmentResult(
            scanned=len(lapsed) + placed.scanned,
            reassigned=reassigned,
            deferred=deferred,
            placed=placed.placed,
        )

    async def _place_unassigned(self) -> _PlacementCount:
        """Give a realtor to requests that never had one (SCRUM-208).

        Excludes anyone already recorded in `declined_realtor_ids` for this
        request — a realtor who let it lapse should not be handed it again by the
        auto-placer, exactly as in the reassignment path above.

        No defer branch: an unassigned row has no window to push out, so "nobody
        available" just means it waits for the next tick or for an admin. Being
        re-examined each pass is the point — the cost is one geo query per row.
        """
        rows = await self._inspections.list_unassigned_for_sweep(limit=self._batch_limit)
        placed = 0
        for item in rows:
            realtor_id = await self._realtors.find_nearest_approved(
                listing_id=item.listing_id,
                radius_m=self._radius_meters,
                exclude=list(item.declined_realtor_ids),
            )
            if realtor_id is None:
                continue
            if await self._inspections.place(
                item.inspection_id, realtor_id=realtor_id, window_hours=self._window_hours
            ):
                placed += 1
                logger.info(
                    "inspection.placed_by_sweep",
                    extra={
                        "inspection_id": str(item.inspection_id),
                        "realtor_id": str(realtor_id),
                    },
                )
                # Best-effort, as above: a broker outage must not undo a placement
                # that is already committed to the row.
                await self._notifier.assigned(
                    realtor_id=realtor_id, inspection_id=item.inspection_id
                )
        return _PlacementCount(scanned=len(rows), placed=placed)
