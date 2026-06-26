"""Response schemas for loan repayment tracking (SCRUM-77)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.services.repayment_query import (
    ActiveLoanItem,
    LoanRepaymentsView,
    MilestoneView,
    RepaymentProgress,
)


class RepaymentProgressOut(BaseModel):
    milestone_count: int
    paid_count: int
    overdue_count: int
    total_due_kobo: int
    total_paid_kobo: int
    next_due_date: date | None

    @classmethod
    def from_progress(cls, p: RepaymentProgress) -> RepaymentProgressOut:
        return cls(
            milestone_count=p.milestone_count,
            paid_count=p.paid_count,
            overdue_count=p.overdue_count,
            total_due_kobo=p.total_due_kobo,
            total_paid_kobo=p.total_paid_kobo,
            next_due_date=p.next_due_date,
        )


class MilestoneOut(BaseModel):
    due_date: date
    amount_due_kobo: int
    amount_paid_kobo: int
    status: str
    is_overdue: bool
    paid_at: datetime | None
    bank_reference: str | None

    @classmethod
    def from_view(cls, m: MilestoneView) -> MilestoneOut:
        return cls(
            due_date=m.due_date,
            amount_due_kobo=m.amount_due_kobo,
            amount_paid_kobo=m.amount_paid_kobo,
            status=m.status,
            is_overdue=m.is_overdue,
            paid_at=m.paid_at,
            bank_reference=m.bank_reference,
        )


class LoanRepaymentsOut(BaseModel):
    loan_id: UUID
    status: str
    requested_amount_kobo: int
    title_released: bool
    progress: RepaymentProgressOut
    milestones: list[MilestoneOut]

    @classmethod
    def from_view(cls, v: LoanRepaymentsView) -> LoanRepaymentsOut:
        return cls(
            loan_id=v.loan_id,
            status=v.status,
            requested_amount_kobo=v.requested_amount_kobo,
            title_released=v.title_released,
            progress=RepaymentProgressOut.from_progress(v.progress),
            milestones=[MilestoneOut.from_view(m) for m in v.milestones],
        )


class ActiveLoanOut(BaseModel):
    loan_id: UUID
    buyer_id: UUID
    transaction_id: UUID
    status: str
    requested_amount_kobo: int
    title_released: bool
    created_at: datetime
    progress: RepaymentProgressOut

    @classmethod
    def from_item(cls, i: ActiveLoanItem) -> ActiveLoanOut:
        return cls(
            loan_id=i.loan_id,
            buyer_id=i.buyer_id,
            transaction_id=i.transaction_id,
            status=i.status,
            requested_amount_kobo=i.requested_amount_kobo,
            title_released=i.title_released,
            created_at=i.created_at,
            progress=RepaymentProgressOut.from_progress(i.progress),
        )


class ActiveLoansOut(BaseModel):
    items: list[ActiveLoanOut]
