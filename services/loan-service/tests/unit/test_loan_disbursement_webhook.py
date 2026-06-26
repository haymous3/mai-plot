"""Unit tests for LoanDisbursementWebhookService (SCRUM-129)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.loan_repo import LoanRow
from app.services.loan_disbursement_webhook import (
    DisbursementOutcome,
    LoanDisbursementWebhookService,
)

pytestmark = pytest.mark.asyncio


def _loan(
    *,
    status: str = "approved",
    approved_amount_kobo: int | None = 200_000_000,
    buyer: UUID | None = None,
    tx: UUID | None = None,
) -> LoanRow:
    return LoanRow(
        id=uuid4(),
        transaction_id=tx or uuid4(),
        buyer_id=buyer or uuid4(),
        bank_partner_id=uuid4(),
        requested_amount_kobo=250_000_000,
        tenure_months=12,
        status=status,
        bank_reference_id="BANK-REF-9",
        created_at=datetime.now(UTC),
        approved_amount_kobo=approved_amount_kobo,
    )


class _StubLoans:
    def __init__(self, *, loan: LoanRow | None, opened_ok: bool = True, disbursed_ok: bool = True):
        self._loan = loan
        self._opened_ok = opened_ok
        self._disbursed_ok = disbursed_ok
        self.opened_calls: list[UUID] = []
        self.disbursed_calls: list[UUID] = []

    async def get_by_bank_reference(self, bank_reference_id: str) -> LoanRow | None:
        return self._loan

    async def mark_account_opened(self, loan_id: UUID) -> bool:
        self.opened_calls.append(loan_id)
        return self._opened_ok

    async def mark_disbursed(self, loan_id: UUID) -> bool:
        self.disbursed_calls.append(loan_id)
        return self._disbursed_ok


class _StubNotifier:
    def __init__(self) -> None:
        self.opened: list[dict[str, object]] = []
        self.disbursed_calls: list[dict[str, object]] = []

    async def loan_decision(self, **kwargs: object) -> None:
        return None

    async def title_released(self, **kwargs: object) -> None:
        return None

    async def account_opened(self, **kwargs: object) -> None:
        self.opened.append(kwargs)

    async def disbursed(self, **kwargs: object) -> None:
        self.disbursed_calls.append(kwargs)


class _StubTxTasks:
    def __init__(self, *, raises: bool = False) -> None:
        self.credits: list[dict[str, object]] = []
        self._raises = raises

    def credit_loan_disbursement(self, **kwargs: object) -> None:
        if self._raises:
            raise RuntimeError("broker down")
        self.credits.append(kwargs)

    def advance_loan_decision(self, **kwargs: object) -> None:
        return None


def _service(
    loans: _StubLoans, notifier: _StubNotifier, tx_tasks: _StubTxTasks | None = None
) -> LoanDisbursementWebhookService:
    return LoanDisbursementWebhookService(
        loans=loans,  # type: ignore[arg-type]
        notifier=notifier,
        tx_tasks=tx_tasks or _StubTxTasks(),
    )


def _payload(event: str, **data: object) -> dict[str, object]:
    base: dict[str, object] = {"reference": "BANK-REF-9"}
    base.update(data)
    return {"event": event, "data": base}


# ---- account.opened -------------------------------------------------------


async def test_account_opened_sets_flag_and_notifies() -> None:
    buyer = uuid4()
    loans = _StubLoans(loan=_loan(buyer=buyer))
    notifier = _StubNotifier()
    outcome = await _service(loans, notifier).handle_account_opened(_payload("account.opened"))
    assert outcome is DisbursementOutcome.account_opened
    assert loans.opened_calls  # the flag flip was attempted
    assert notifier.opened[0]["buyer_id"] == buyer


async def test_account_opened_duplicate() -> None:
    loans = _StubLoans(loan=_loan(), opened_ok=False)  # already opened
    notifier = _StubNotifier()
    outcome = await _service(loans, notifier).handle_account_opened(_payload("account.opened"))
    assert outcome is DisbursementOutcome.duplicate
    assert notifier.opened == []


async def test_account_opened_unknown_loan() -> None:
    outcome = await _service(_StubLoans(loan=None), _StubNotifier()).handle_account_opened(
        _payload("account.opened")
    )
    assert outcome is DisbursementOutcome.unknown_loan


async def test_account_opened_missing_reference_ignored() -> None:
    outcome = await _service(_StubLoans(loan=_loan()), _StubNotifier()).handle_account_opened(
        {"event": "account.opened", "data": {}}
    )
    assert outcome is DisbursementOutcome.ignored


# ---- loan.disbursed -------------------------------------------------------


async def test_disbursed_marks_enqueues_credit_and_notifies() -> None:
    buyer, tx = uuid4(), uuid4()
    loans = _StubLoans(loan=_loan(buyer=buyer, tx=tx, approved_amount_kobo=200_000_000))
    notifier, tx_tasks = _StubNotifier(), _StubTxTasks()
    outcome = await _service(loans, notifier, tx_tasks).handle_disbursed(_payload("loan.disbursed"))
    assert outcome is DisbursementOutcome.disbursed
    assert loans.disbursed_calls  # approved → disbursed flip
    credit = tx_tasks.credits[0]
    assert credit["transaction_id"] == tx
    assert credit["buyer_id"] == buyer
    assert credit["amount_kobo"] == 200_000_000
    assert notifier.disbursed_calls[0]["amount_kobo"] == 200_000_000


async def test_disbursed_not_approved_is_duplicate() -> None:
    # Already disbursed (status != approved) → no flip, no credit.
    loans = _StubLoans(loan=_loan(status="disbursed"))
    tx_tasks = _StubTxTasks()
    outcome = await _service(loans, _StubNotifier(), tx_tasks).handle_disbursed(
        _payload("loan.disbursed")
    )
    assert outcome is DisbursementOutcome.duplicate
    assert tx_tasks.credits == []


async def test_disbursed_missing_approved_amount_is_duplicate() -> None:
    # An 'approved' loan with no approved amount is a data anomaly — don't credit blind.
    loans = _StubLoans(loan=_loan(approved_amount_kobo=None))
    outcome = await _service(loans, _StubNotifier(), _StubTxTasks()).handle_disbursed(
        _payload("loan.disbursed")
    )
    assert outcome is DisbursementOutcome.duplicate
    assert loans.disbursed_calls == []  # never flipped


async def test_disbursed_lost_race_is_duplicate() -> None:
    # mark_disbursed matched 0 rows (a concurrent webhook won) → duplicate, no credit.
    loans = _StubLoans(loan=_loan(), disbursed_ok=False)
    tx_tasks = _StubTxTasks()
    outcome = await _service(loans, _StubNotifier(), tx_tasks).handle_disbursed(
        _payload("loan.disbursed")
    )
    assert outcome is DisbursementOutcome.duplicate
    assert tx_tasks.credits == []


async def test_disbursed_credit_enqueue_failure_propagates() -> None:
    # An escrow credit must never be silently lost: a broker outage raises so the
    # request transaction rolls back and the bank retries.
    loans = _StubLoans(loan=_loan())
    with pytest.raises(RuntimeError):
        await _service(loans, _StubNotifier(), _StubTxTasks(raises=True)).handle_disbursed(
            _payload("loan.disbursed")
        )


async def test_disbursed_unknown_loan() -> None:
    outcome = await _service(_StubLoans(loan=None), _StubNotifier()).handle_disbursed(
        _payload("loan.disbursed")
    )
    assert outcome is DisbursementOutcome.unknown_loan
