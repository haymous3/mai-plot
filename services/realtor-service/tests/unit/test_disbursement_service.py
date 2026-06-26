"""Unit tests for the commission DisbursementService sweep (SCRUM-86 PR-B)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.commission_repo import DisbursableCommission
from app.services.disbursement_service import DisbursementService

pytestmark = pytest.mark.asyncio


def _commission(transaction_id: UUID | None = None) -> DisbursableCommission:
    return DisbursableCommission(
        commission_id=uuid4(),
        transaction_id=transaction_id or uuid4(),
        realtor_id=uuid4(),
        seller_id=uuid4(),
        amount_kobo=100_000_000,
    )


class _StubCommissions:
    def __init__(
        self,
        disbursable: list[DisbursableCommission],
        *,
        completed: dict[UUID, UUID] | None = None,
        mark_ok: bool = True,
    ) -> None:
        self._disbursable = disbursable
        self._completed = completed or {}
        self._mark_ok = mark_ok
        self.withdrawn: list[UUID] = []

    async def list_disbursable(self, *, limit: int = 500) -> list[DisbursableCommission]:
        return self._disbursable

    async def completed_disbursement(self, transaction_id: UUID) -> UUID | None:
        return self._completed.get(transaction_id)

    async def mark_withdrawn(self, transaction_id: UUID, *, payment_event_id: UUID) -> bool:
        self.withdrawn.append(transaction_id)
        return self._mark_ok


class _StubProducer:
    def __init__(self) -> None:
        self.requested: list[UUID] = []

    async def request_disbursement(
        self,
        *,
        commission_id: UUID,
        transaction_id: UUID,
        realtor_id: UUID,
        seller_id: UUID,
        amount_kobo: int,
    ) -> None:
        self.requested.append(transaction_id)


def _service(commissions: _StubCommissions, producer: _StubProducer) -> DisbursementService:
    return DisbursementService(
        commissions=commissions,
        producer=producer,
    )


async def test_enqueues_when_no_completed_payout() -> None:
    c = _commission()
    commissions = _StubCommissions([c])  # no completed payout
    producer = _StubProducer()

    result = await _service(commissions, producer).run()

    assert result.requested == 1
    assert result.withdrawn == 0
    assert producer.requested == [c.transaction_id]
    assert commissions.withdrawn == []  # not flipped — payout not done


async def test_reconciles_completed_payout_to_withdrawn() -> None:
    c = _commission()
    pe = uuid4()
    commissions = _StubCommissions([c], completed={c.transaction_id: pe})
    producer = _StubProducer()

    result = await _service(commissions, producer).run()

    assert result.withdrawn == 1
    assert result.requested == 0
    assert commissions.withdrawn == [c.transaction_id]
    assert producer.requested == []  # no re-enqueue once paid


async def test_lost_race_does_not_count_withdrawn() -> None:
    c = _commission()
    commissions = _StubCommissions([c], completed={c.transaction_id: uuid4()}, mark_ok=False)

    result = await _service(commissions, _StubProducer()).run()

    assert result.withdrawn == 0  # mark_withdrawn returned False (already done)


async def test_empty_sweep_is_noop() -> None:
    result = await _service(_StubCommissions([]), _StubProducer()).run()
    assert result.scanned == 0 and result.withdrawn == 0 and result.requested == 0
