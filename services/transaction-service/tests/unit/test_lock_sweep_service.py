"""Unit tests for ListingLockSweepService (SCRUM-149)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.repositories.transaction_repo import LapsedLock
from app.services.lock_sweep import ListingLockSweepService

pytestmark = pytest.mark.asyncio


class _StubTxnRepo:
    def __init__(self, lapsed: list[LapsedLock]) -> None:
        self._lapsed = lapsed
        self.cancelled: list[UUID] = []
        self.events: list[dict[str, Any]] = []

    async def list_lapsed_locks(self, *, limit: int = 500) -> list[LapsedLock]:
        return self._lapsed

    async def update_stage(self, transaction_id: UUID, *, stage: str) -> None:
        assert stage == "cancelled"
        self.cancelled.append(transaction_id)

    async def append_event(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class _StubListingRepo:
    def __init__(self) -> None:
        self.released: list[UUID] = []

    async def release_lock(self, listing_id: UUID) -> None:
        self.released.append(listing_id)


class _StubAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _service(
    lapsed: list[LapsedLock],
) -> tuple[ListingLockSweepService, _StubTxnRepo, _StubListingRepo, _StubAudit]:
    txns, listings, audit = _StubTxnRepo(lapsed), _StubListingRepo(), _StubAudit()
    svc = ListingLockSweepService(
        transactions=txns,  # type: ignore[arg-type]
        listings=listings,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
    )
    return svc, txns, listings, audit


async def test_cancels_each_lapsed_lock_and_reopens_its_listing() -> None:
    lapsed = [
        LapsedLock(transaction_id=uuid4(), listing_id=uuid4()),
        LapsedLock(transaction_id=uuid4(), listing_id=uuid4()),
    ]
    svc, txns, listings, audit = _service(lapsed)

    result = await svc.run()

    assert result.scanned == 2
    assert result.released == 2
    assert txns.cancelled == [lock.transaction_id for lock in lapsed]
    assert listings.released == [lock.listing_id for lock in lapsed]
    # Each cancellation appends a lock_expired event and a system audit entry.
    assert all(e["event_type"] == "lock_expired" for e in txns.events)
    assert all(e["to_stage"] == "cancelled" and e["triggered_by"] is None for e in txns.events)
    assert all(
        r["action"] == "transaction.cancelled" and r["actor_id"] is None for r in audit.records
    )


async def test_nothing_lapsed_is_a_noop() -> None:
    svc, txns, listings, audit = _service([])

    result = await svc.run()

    assert result == type(result)(scanned=0, released=0)
    assert txns.cancelled == []
    assert listings.released == []
    assert audit.records == []
