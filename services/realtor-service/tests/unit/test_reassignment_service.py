"""Unit tests for ReassignmentService (SCRUM-123)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.inspection_repo import LapsedInspection
from app.services.reassignment_service import ReassignmentService

pytestmark = pytest.mark.asyncio


class _StubInspections:
    def __init__(
        self,
        lapsed: list[LapsedInspection],
        *,
        reassign_ok: bool = True,
        unassigned: list[LapsedInspection] | None = None,
        place_ok: bool = True,
    ) -> None:
        self._lapsed = lapsed
        self._reassign_ok = reassign_ok
        # Unassigned requests the sweep may place (SCRUM-208). Empty by default,
        # so the reassignment cases below exercise only the lapsed path.
        self._unassigned = unassigned or []
        self._place_ok = place_ok
        self.reassigned: list[dict[str, object]] = []
        self.deferred: list[UUID] = []
        self.placed: list[dict[str, object]] = []

    async def list_lapsed_pending(self, *, limit: int = 500) -> list[LapsedInspection]:
        return self._lapsed

    async def list_unassigned_for_sweep(self, *, limit: int = 500) -> list[LapsedInspection]:
        return self._unassigned

    async def place(
        self, inspection_id: UUID, *, realtor_id: UUID, window_hours: int
    ) -> object | None:
        self.placed.append({"id": inspection_id, "realtor": realtor_id})
        return object() if self._place_ok else None

    async def reassign(
        self, inspection_id: UUID, *, old_realtor_id: UUID, new_realtor_id: UUID, window_hours: int
    ) -> bool:
        self.reassigned.append({"id": inspection_id, "old": old_realtor_id, "new": new_realtor_id})
        return self._reassign_ok

    async def defer_assignment(self, inspection_id: UUID, *, hours: int) -> bool:
        self.deferred.append(inspection_id)
        return True


class _StubRealtors:
    def __init__(self, next_realtor: UUID | None) -> None:
        self._next = next_realtor
        self.exclude_seen: list[list[UUID]] = []

    async def find_nearest_approved(
        self, *, listing_id: UUID, radius_m: float, exclude: list[UUID] | None = None
    ) -> UUID | None:
        self.exclude_seen.append(list(exclude or []))
        return self._next


class _StubNotifier:
    def __init__(self) -> None:
        self.notified: list[UUID] = []

    async def assigned(self, *, realtor_id: UUID, inspection_id: UUID) -> None:
        self.notified.append(realtor_id)


def _unassigned_row(*, declined: list[UUID] | None = None) -> LapsedInspection:
    """An unassigned request as the sweep sees it: no realtor holds it."""
    return LapsedInspection(
        inspection_id=uuid4(),
        realtor_id=None,
        listing_id=uuid4(),
        declined_realtor_ids=declined or [],
    )


def _lapsed(*, realtor_id: UUID, declined: list[UUID] | None = None) -> LapsedInspection:
    return LapsedInspection(
        inspection_id=uuid4(),
        realtor_id=realtor_id,
        listing_id=uuid4(),
        declined_realtor_ids=declined or [],
    )


def _service(
    inspections: _StubInspections, realtors: _StubRealtors, notifier: _StubNotifier
) -> ReassignmentService:
    return ReassignmentService(
        inspections=inspections,
        realtors=realtors,
        notifier=notifier,
        radius_meters=50_000.0,
        window_hours=2,
        defer_hours=2,
    )


async def test_reassigns_to_next_realtor_and_notifies() -> None:
    current = uuid4()
    nxt = uuid4()
    item = _lapsed(realtor_id=current)
    inspections = _StubInspections([item])
    realtors = _StubRealtors(nxt)
    notifier = _StubNotifier()

    result = await _service(inspections, realtors, notifier).run()

    assert result.scanned == 1
    assert result.reassigned == 1
    assert result.deferred == 0
    assert inspections.reassigned[0] == {"id": item.inspection_id, "old": current, "new": nxt}
    assert notifier.notified == [nxt]


async def test_excludes_current_and_already_declined() -> None:
    current = uuid4()
    prior = uuid4()
    item = _lapsed(realtor_id=current, declined=[prior])
    realtors = _StubRealtors(uuid4())

    await _service(_StubInspections([item]), realtors, _StubNotifier()).run()

    # The proximity query must skip both the prior decliner and the current holder.
    assert realtors.exclude_seen[0] == [prior, current]


async def test_defers_and_does_not_notify_when_nobody_in_range() -> None:
    item = _lapsed(realtor_id=uuid4())
    inspections = _StubInspections([item])
    notifier = _StubNotifier()

    result = await _service(inspections, _StubRealtors(None), notifier).run()

    assert result.reassigned == 0
    assert result.deferred == 1
    assert inspections.deferred == [item.inspection_id]
    assert notifier.notified == []


async def test_no_notify_when_reassign_guard_loses_race() -> None:
    # reassign() returns False (someone accepted between scan and update) -> the
    # realtor must NOT be told they were assigned.
    item = _lapsed(realtor_id=uuid4())
    notifier = _StubNotifier()

    result = await _service(
        _StubInspections([item], reassign_ok=False), _StubRealtors(uuid4()), notifier
    ).run()

    assert result.reassigned == 0
    assert notifier.notified == []


async def test_empty_sweep_is_noop() -> None:
    result = await _service(_StubInspections([]), _StubRealtors(None), _StubNotifier()).run()
    assert result == result.__class__(scanned=0, reassigned=0, deferred=0)


# --- placing unassigned requests (SCRUM-208) ---------------------------------


async def test_places_an_unassigned_request_and_notifies() -> None:
    """The dropped-request fallback is self-healing: a realtor who becomes
    eligible picks up the backlog on the next tick, with no admin involved."""
    realtor = uuid4()
    row = _unassigned_row()
    inspections = _StubInspections([], unassigned=[row])
    realtors = _StubRealtors(realtor)
    notifier = _StubNotifier()

    result = await _service(inspections, realtors, notifier).run()

    assert result.placed == 1
    assert inspections.placed == [{"id": row.inspection_id, "realtor": realtor}]
    assert notifier.notified == [realtor]
    # Nothing was taken from anybody, so this is not a reassignment.
    assert result.reassigned == 0
    assert inspections.reassigned == []


async def test_unassigned_request_excludes_realtors_who_already_lapsed_it() -> None:
    declined = uuid4()
    inspections = _StubInspections([], unassigned=[_unassigned_row(declined=[declined])])
    realtors = _StubRealtors(uuid4())

    await _service(inspections, realtors, _StubNotifier()).run()

    assert realtors.exclude_seen == [[declined]]


async def test_unassigned_request_stays_when_nobody_is_available() -> None:
    """No defer branch: an unassigned row has no window to push out, so it simply
    waits for the next tick or for an admin. It must NOT be counted as deferred
    or touched at all."""
    inspections = _StubInspections([], unassigned=[_unassigned_row()])
    notifier = _StubNotifier()

    result = await _service(inspections, _StubRealtors(None), notifier).run()

    assert result.placed == 0
    assert inspections.placed == []
    assert inspections.deferred == []
    assert notifier.notified == []


async def test_no_notify_when_the_placement_guard_loses_the_race() -> None:
    """An admin placed it first: the guarded UPDATE returns nothing, so the
    realtor we picked must not be told they have an assignment they do not."""
    inspections = _StubInspections([], unassigned=[_unassigned_row()], place_ok=False)
    notifier = _StubNotifier()

    result = await _service(inspections, _StubRealtors(uuid4()), notifier).run()

    assert result.placed == 0
    assert notifier.notified == []
