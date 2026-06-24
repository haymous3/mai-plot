"""Unit tests for ReassignmentService (SCRUM-123)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.inspection_repo import LapsedInspection
from app.services.reassignment_service import ReassignmentService

pytestmark = pytest.mark.asyncio


class _StubInspections:
    def __init__(self, lapsed: list[LapsedInspection], *, reassign_ok: bool = True) -> None:
        self._lapsed = lapsed
        self._reassign_ok = reassign_ok
        self.reassigned: list[dict[str, object]] = []
        self.deferred: list[UUID] = []

    async def list_lapsed_pending(self, *, limit: int = 500) -> list[LapsedInspection]:
        return self._lapsed

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
