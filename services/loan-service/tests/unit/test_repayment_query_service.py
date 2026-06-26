"""Unit tests for RepaymentQueryService (SCRUM-77) — overdue derivation + access."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.repositories.loan_repo import LoanRow
from app.repositories.repayment_repo import MilestoneRow
from app.security import CurrentUser
from app.services.repayment_query import (
    LoanNotFound,
    NotLoanViewer,
    RepaymentQueryService,
)

pytestmark = pytest.mark.asyncio


def _loan(*, buyer: UUID, title_released: bool = False) -> LoanRow:
    return LoanRow(
        id=uuid4(),
        transaction_id=uuid4(),
        buyer_id=buyer,
        bank_partner_id=uuid4(),
        requested_amount_kobo=250_000_000,
        tenure_months=12,
        status="repaying",
        bank_reference_id="BANK-REF-9",
        created_at=datetime.now(UTC),
        title_released_at=datetime.now(UTC) if title_released else None,
    )


def _milestone(*, loan_id: UUID, due: date, status: str, paid: int = 0) -> MilestoneRow:
    return MilestoneRow(
        id=uuid4(),
        loan_id=loan_id,
        due_date=due,
        amount_due_kobo=10_000_000,
        amount_paid_kobo=paid,
        status=status,
        paid_at=None,
        bank_reference=None,
    )


class _StubLoans:
    def __init__(self, *, loan: LoanRow | None) -> None:
        self._loan = loan

    async def get(self, loan_id: UUID) -> LoanRow | None:
        return self._loan


class _StubMilestones:
    def __init__(self, *, rows: list[MilestoneRow]) -> None:
        self._rows = rows

    async def list_for_loan(self, loan_id: UUID) -> list[MilestoneRow]:
        return self._rows


def _service(loan: LoanRow | None, rows: list[MilestoneRow]) -> RepaymentQueryService:
    return RepaymentQueryService(
        loans=_StubLoans(loan=loan),  # type: ignore[arg-type]
        milestones=_StubMilestones(rows=rows),  # type: ignore[arg-type]
    )


async def test_not_found() -> None:
    with pytest.raises(LoanNotFound):
        await _service(None, []).get_for_loan(uuid4(), CurrentUser(user_id=uuid4(), role="buyer"))


async def test_non_owner_buyer_forbidden() -> None:
    loan = _loan(buyer=uuid4())
    with pytest.raises(NotLoanViewer):
        await _service(loan, []).get_for_loan(loan.id, CurrentUser(user_id=uuid4(), role="buyer"))


async def test_admin_may_view_any_loan() -> None:
    loan = _loan(buyer=uuid4())
    view = await _service(loan, []).get_for_loan(
        loan.id, CurrentUser(user_id=uuid4(), role="admin")
    )
    assert view.loan_id == loan.id


async def test_progress_and_overdue_derivation() -> None:
    buyer = uuid4()
    loan = _loan(buyer=buyer)
    today = date.today()
    rows = [
        _milestone(loan_id=loan.id, due=today - timedelta(days=30), status="paid", paid=10_000_000),
        _milestone(loan_id=loan.id, due=today - timedelta(days=1), status="pending"),  # overdue
        _milestone(loan_id=loan.id, due=today + timedelta(days=30), status="pending"),  # future
    ]
    view = await _service(loan, rows).get_for_loan(
        loan.id, CurrentUser(user_id=buyer, role="buyer")
    )
    assert view.progress.milestone_count == 3
    assert view.progress.paid_count == 1
    assert view.progress.overdue_count == 1
    assert view.progress.total_due_kobo == 30_000_000
    assert view.progress.total_paid_kobo == 10_000_000
    assert view.progress.next_due_date == today - timedelta(days=1)  # earliest unpaid
    # the past-due pending milestone is flagged overdue; the future one is not
    overdue_flags = {m.due_date: m.is_overdue for m in view.milestones}
    assert overdue_flags[today - timedelta(days=1)] is True
    assert overdue_flags[today + timedelta(days=30)] is False
    assert overdue_flags[today - timedelta(days=30)] is False  # paid, not overdue
