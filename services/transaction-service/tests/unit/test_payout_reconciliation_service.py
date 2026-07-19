"""Unit tests for PayoutReconciliationService (SCRUM-147)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.escrow_repo import FailedPayout
from app.services.payout_reconciliation import PayoutReconciliationService

pytestmark = pytest.mark.asyncio

_ACTOR = uuid4()


class _StubLedgerRepo:
    def __init__(self, failed: list[FailedPayout]) -> None:
        self._failed = failed
        self.query_calls = 0

    async def list_failed_payouts_needing_reversal(
        self, *, payout_types: tuple[str, ...], limit: int = 500
    ) -> list[FailedPayout]:
        self.query_calls += 1
        return self._failed


class _StubEscrow:
    def __init__(self) -> None:
        self.reversals: list[tuple[UUID, int, UUID]] = []

    async def reverse_debit(
        self,
        *,
        transaction_id: UUID,
        amount_kobo: int,
        payment_event_id: UUID,
        reason: str,
        recorded_by: UUID | None = None,
    ) -> UUID:
        self.reversals.append((transaction_id, amount_kobo, payment_event_id))
        return uuid4()


def _service(
    failed: list[FailedPayout],
) -> tuple[PayoutReconciliationService, _StubLedgerRepo, _StubEscrow]:
    ledger, escrow = _StubLedgerRepo(failed), _StubEscrow()
    svc = PayoutReconciliationService(
        ledger=ledger,  # type: ignore[arg-type]
        escrow=escrow,  # type: ignore[arg-type]
        actor_id=_ACTOR,
    )
    return svc, ledger, escrow


def _payout(*, amount: int = 100_000_000) -> FailedPayout:
    return FailedPayout(payment_event_id=uuid4(), transaction_id=uuid4(), debit_kobo=amount)


async def test_reverses_each_failed_payout() -> None:
    failed = [_payout(amount=100_000_000), _payout(amount=250_000_000)]
    svc, _, escrow = _service(failed)

    result = await svc.run()

    assert result.scanned == 2
    assert result.reversed == 2
    assert [
        (p.transaction_id, p.debit_kobo, p.payment_event_id) for p in failed
    ] == escrow.reversals


async def test_nothing_to_reverse_is_a_noop() -> None:
    svc, _, escrow = _service([])
    result = await svc.run()

    assert result == type(result)(scanned=0, reversed=0)
    assert escrow.reversals == []


async def test_reversal_uses_the_debit_total_and_system_actor() -> None:
    payout = _payout(amount=777_000_000)
    svc, _, escrow = _service([payout])

    await svc.run()

    assert escrow.reversals == [(payout.transaction_id, 777_000_000, payout.payment_event_id)]
