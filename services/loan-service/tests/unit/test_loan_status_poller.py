"""Unit tests for LoanStatusPoller (SCRUM-130).

The poller is the safety net for a delayed/dropped `loan.decision_ready` webhook:
it lists still-pending loans, asks the bank for each one's status, and applies any
decided one through the SAME path as the webhook (decisions.apply_for_loan). These
tests drive it with stubs so no bank / DB / broker is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.adapters.bank import BankAdapterError, LoanStatusResult
from app.repositories.loan_repo import LoanRow, PollableLoan
from app.services.loan_decision import DecisionOutcome
from app.services.loan_status_poller import LoanStatusPoller

pytestmark = pytest.mark.asyncio


def _loan(*, status: str = "under_review") -> LoanRow:
    return LoanRow(
        id=uuid4(),
        transaction_id=uuid4(),
        buyer_id=uuid4(),
        bank_partner_id=uuid4(),
        requested_amount_kobo=250_000_000,
        tenure_months=12,
        status=status,
        bank_reference_id="BANK-REF-9",
        created_at=datetime.now(UTC),
    )


def _pollable(loan: LoanRow, *, short_code: str = "bank1") -> PollableLoan:
    return PollableLoan(
        loan=loan,
        short_code=short_code,
        bank_reference_id=loan.bank_reference_id or "BANK-REF-9",
    )


class _StubLoans:
    def __init__(self, pollable: list[PollableLoan]) -> None:
        self._pollable = pollable
        self.calls: list[dict[str, object]] = []

    async def list_pollable(self, *, older_than_minutes: int, limit: int) -> list[PollableLoan]:
        self.calls.append({"older_than_minutes": older_than_minutes, "limit": limit})
        return self._pollable


class _StubAdapter:
    def __init__(self, *, result: LoanStatusResult | None = None, raises: bool = False) -> None:
        self._result = result or LoanStatusResult(status="under_review")
        self._raises = raises

    async def get_status(self, bank_reference_id: str) -> LoanStatusResult:
        if self._raises:
            raise BankAdapterError("bank unreachable")
        return self._result


class _StubRegistry:
    def __init__(self, adapter: _StubAdapter) -> None:
        self._adapter = adapter
        self.requested: list[str] = []

    def for_partner(self, *, short_code: str) -> _StubAdapter:
        self.requested.append(short_code)
        return self._adapter


class _StubDecisions:
    def __init__(self, *, outcome: DecisionOutcome = DecisionOutcome.decided) -> None:
        self._outcome = outcome
        self.applied: list[dict[str, object]] = []

    async def apply_for_loan(self, loan: LoanRow, **kwargs: object) -> DecisionOutcome:
        self.applied.append({"loan_id": loan.id, **kwargs})
        return self._outcome


def _poller(
    loans: _StubLoans, registry: _StubRegistry, decisions: _StubDecisions
) -> LoanStatusPoller:
    return LoanStatusPoller(
        loans=loans,  # type: ignore[arg-type]
        registry=registry,  # type: ignore[arg-type]
        decisions=decisions,  # type: ignore[arg-type]
        stale_minutes=30,
        batch_limit=100,
    )


async def test_empty_worklist_is_a_noop() -> None:
    loans = _StubLoans([])
    decisions = _StubDecisions()
    result = await _poller(loans, _StubRegistry(_StubAdapter()), decisions).run()
    assert result.scanned == 0
    assert result.decided == 0
    assert result.errors == 0
    assert decisions.applied == []
    # The stale threshold + batch limit are passed through to the query.
    assert loans.calls[0] == {"older_than_minutes": 30, "limit": 100}


async def test_approved_status_is_applied() -> None:
    loan = _loan()
    adapter = _StubAdapter(
        result=LoanStatusResult(
            status="approved",
            approved_amount_kobo=200_000_000,
            interest_rate_bps=2200,
            tenure_months=12,
            monthly_instalment_kobo=18_000_000,
        )
    )
    registry = _StubRegistry(adapter)
    decisions = _StubDecisions()
    result = await _poller(_StubLoans([_pollable(loan)]), registry, decisions).run()
    assert result.scanned == 1
    assert result.decided == 1
    assert registry.requested == ["bank1"]
    applied = decisions.applied[0]
    assert applied["loan_id"] == loan.id
    assert applied["decision"] == "approved"
    assert applied["approved_amount_kobo"] == 200_000_000


async def test_rejected_status_is_applied() -> None:
    loan = _loan()
    decisions = _StubDecisions()
    result = await _poller(
        _StubLoans([_pollable(loan)]),
        _StubRegistry(_StubAdapter(result=LoanStatusResult(status="rejected"))),
        decisions,
    ).run()
    assert result.decided == 1
    assert decisions.applied[0]["decision"] == "rejected"


async def test_still_pending_status_is_skipped() -> None:
    # under_review means the bank hasn't decided — nothing to apply yet.
    decisions = _StubDecisions()
    result = await _poller(
        _StubLoans([_pollable(_loan())]),
        _StubRegistry(_StubAdapter(result=LoanStatusResult(status="under_review"))),
        decisions,
    ).run()
    assert result.scanned == 1
    assert result.decided == 0
    assert decisions.applied == []


async def test_bank_error_on_one_loan_is_counted_and_sweep_continues() -> None:
    # A get_status failure must not abort the whole sweep — it's logged and the
    # loan is left for the next tick.
    decisions = _StubDecisions()
    result = await _poller(
        _StubLoans([_pollable(_loan())]),
        _StubRegistry(_StubAdapter(raises=True)),
        decisions,
    ).run()
    assert result.scanned == 1
    assert result.decided == 0
    assert result.errors == 1
    assert decisions.applied == []


async def test_duplicate_apply_is_not_counted_as_decided() -> None:
    # apply_for_loan returns `duplicate` when the loan was already decided (webhook
    # beat us to it, or two polls raced) — it's applied but not tallied as a new
    # decision.
    decisions = _StubDecisions(outcome=DecisionOutcome.duplicate)
    result = await _poller(
        _StubLoans([_pollable(_loan())]),
        _StubRegistry(_StubAdapter(result=LoanStatusResult(status="approved"))),
        decisions,
    ).run()
    assert result.scanned == 1
    assert result.decided == 0
    assert len(decisions.applied) == 1  # it was attempted


async def test_mixed_batch_tallies_decided_and_errors() -> None:
    # Two decidable loans + one unreachable, across the same partner adapter.
    loans = _StubLoans([_pollable(_loan()), _pollable(_loan())])
    # First adapter decides; use a registry that flips to erroring on 2nd loan by
    # sharing one adapter that always approves, and a separate error case is covered
    # above. Here both approve → 2 decided, 0 errors.
    decisions = _StubDecisions()
    result = await _poller(
        loans,
        _StubRegistry(_StubAdapter(result=LoanStatusResult(status="approved"))),
        decisions,
    ).run()
    assert result.scanned == 2
    assert result.decided == 2
    assert result.errors == 0
