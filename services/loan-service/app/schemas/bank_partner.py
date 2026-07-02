"""Response schemas for the buyer bank-partner list (SCRUM-94)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.repositories.bank_partner_repo import BankPartnerSummary


class BankPartnerItem(BaseModel):
    id: UUID
    name: str
    short_code: str
    loan_min_kobo: int
    loan_max_kobo: int
    interest_rate_bps: int
    min_tenure_months: int
    max_tenure_months: int
    requires_account_opening: bool

    @classmethod
    def from_summary(cls, s: BankPartnerSummary) -> BankPartnerItem:
        return cls(
            id=s.id,
            name=s.name,
            short_code=s.short_code,
            loan_min_kobo=s.loan_min_kobo,
            loan_max_kobo=s.loan_max_kobo,
            interest_rate_bps=s.interest_rate_bps,
            min_tenure_months=s.min_tenure_months,
            max_tenure_months=s.max_tenure_months,
            requires_account_opening=s.requires_account_opening,
        )


class BankPartnersResponse(BaseModel):
    items: list[BankPartnerItem]
