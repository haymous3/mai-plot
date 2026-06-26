"""Read side for loan repayment tracking (SCRUM-77).

Powers the buyer's repayment-progress view (a buyer sees only their own loan) and
the admin active-loans view. Overdue is derived here, not stored: a milestone is
overdue when it is still pending and its due_date is in the past.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.repositories.loan_repo import LoanRepository, LoanRow
from app.repositories.repayment_repo import (
    MilestoneRow,
    RepaymentMilestoneRepository,
    RepaymentRollup,
)
from app.security import CurrentUser


class RepaymentQueryError(RuntimeError):
    pass


class LoanNotFound(RepaymentQueryError):
    pass


class NotLoanViewer(RepaymentQueryError):
    """Only the loan's buyer (or an admin) may view its repayments."""


@dataclass(frozen=True)
class MilestoneView:
    due_date: date
    amount_due_kobo: int
    amount_paid_kobo: int
    status: str
    is_overdue: bool
    paid_at: datetime | None
    bank_reference: str | None


@dataclass(frozen=True)
class RepaymentProgress:
    milestone_count: int
    paid_count: int
    overdue_count: int
    total_due_kobo: int
    total_paid_kobo: int
    next_due_date: date | None


@dataclass(frozen=True)
class LoanRepaymentsView:
    loan_id: UUID
    status: str
    requested_amount_kobo: int
    title_released: bool
    progress: RepaymentProgress
    milestones: list[MilestoneView]


@dataclass(frozen=True)
class ActiveLoanItem:
    loan_id: UUID
    buyer_id: UUID
    transaction_id: UUID
    status: str
    requested_amount_kobo: int
    title_released: bool
    created_at: datetime
    progress: RepaymentProgress


class RepaymentQueryService:
    def __init__(self, *, loans: LoanRepository, milestones: RepaymentMilestoneRepository) -> None:
        self._loans = loans
        self._milestones = milestones

    async def get_for_loan(self, loan_id: UUID, caller: CurrentUser) -> LoanRepaymentsView:
        loan = await self._loans.get(loan_id)
        if loan is None:
            raise LoanNotFound()
        if caller.role != "admin" and loan.buyer_id != caller.user_id:
            raise NotLoanViewer()

        rows = await self._milestones.list_for_loan(loan_id)
        today = date.today()
        return LoanRepaymentsView(
            loan_id=loan.id,
            status=loan.status,
            requested_amount_kobo=loan.requested_amount_kobo,
            title_released=loan.title_released_at is not None,
            progress=self._progress(rows, today),
            milestones=[self._view(r, today) for r in rows],
        )

    async def list_active(self, *, limit: int, offset: int) -> list[ActiveLoanItem]:
        loans = await self._loans.list_active(limit=limit, offset=offset)
        rollups = await self._milestones.rollup_for_loans([loan.id for loan in loans])
        return [self._active_item(loan, rollups) for loan in loans]

    @staticmethod
    def _view(row: MilestoneRow, today: date) -> MilestoneView:
        return MilestoneView(
            due_date=row.due_date,
            amount_due_kobo=row.amount_due_kobo,
            amount_paid_kobo=row.amount_paid_kobo,
            status=row.status,
            is_overdue=row.status == "pending" and row.due_date < today,
            paid_at=row.paid_at,
            bank_reference=row.bank_reference,
        )

    @staticmethod
    def _progress(rows: list[MilestoneRow], today: date) -> RepaymentProgress:
        unpaid_due = [r.due_date for r in rows if r.status != "paid"]
        return RepaymentProgress(
            milestone_count=len(rows),
            paid_count=sum(1 for r in rows if r.status == "paid"),
            overdue_count=sum(1 for r in rows if r.status == "pending" and r.due_date < today),
            total_due_kobo=sum(r.amount_due_kobo for r in rows),
            total_paid_kobo=sum(r.amount_paid_kobo for r in rows),
            next_due_date=min(unpaid_due, default=None),
        )

    @staticmethod
    def _active_item(loan: LoanRow, rollups: dict[UUID, RepaymentRollup]) -> ActiveLoanItem:
        roll = rollups.get(loan.id)
        progress = (
            RepaymentProgress(
                milestone_count=roll.milestone_count,
                paid_count=roll.paid_count,
                overdue_count=roll.overdue_count,
                total_due_kobo=roll.total_due_kobo,
                total_paid_kobo=roll.total_paid_kobo,
                next_due_date=None,
            )
            if roll is not None
            else RepaymentProgress(0, 0, 0, 0, 0, None)
        )
        return ActiveLoanItem(
            loan_id=loan.id,
            buyer_id=loan.buyer_id,
            transaction_id=loan.transaction_id,
            status=loan.status,
            requested_amount_kobo=loan.requested_amount_kobo,
            title_released=loan.title_released_at is not None,
            created_at=loan.created_at,
            progress=progress,
        )
