"""Response schema for the buyer loan-detail / status page (SCRUM-94)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.repositories.loan_repo import LoanDetailRow


class LoanDetailOut(BaseModel):
    loan_id: UUID
    transaction_id: UUID
    status: str
    requested_amount_kobo: int
    approved_amount_kobo: int | None
    interest_rate_bps: int | None
    tenure_months: int | None
    monthly_instalment_kobo: int | None
    bank_name: str
    requires_account_opening: bool
    bank_account_opened: bool
    bank_decision_at: datetime | None
    created_at: datetime
    title_released: bool
    employment_status: str | None
    monthly_income_kobo: int | None

    @classmethod
    def from_row(cls, r: LoanDetailRow) -> LoanDetailOut:
        return cls(
            loan_id=r.id,
            transaction_id=r.transaction_id,
            status=r.status,
            requested_amount_kobo=r.requested_amount_kobo,
            approved_amount_kobo=r.approved_amount_kobo,
            interest_rate_bps=r.interest_rate_bps,
            tenure_months=r.tenure_months,
            monthly_instalment_kobo=r.monthly_instalment_kobo,
            bank_name=r.bank_name,
            requires_account_opening=r.requires_account_opening,
            bank_account_opened=r.bank_account_opened,
            bank_decision_at=r.bank_decision_at,
            created_at=r.created_at,
            title_released=r.title_released_at is not None,
            employment_status=r.employment_status,
            monthly_income_kobo=r.monthly_income_kobo,
        )
