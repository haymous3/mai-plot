"""Request/response schemas for the loan application workflow (SCRUM-75)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.repositories.loan_repo import LoanRow

EmploymentStatus = Literal["employed", "self_employed", "business_owner", "unemployed"]


class LoanApplyRequest(BaseModel):
    transaction_id: UUID
    bank_partner_id: UUID
    requested_amount_kobo: int = Field(gt=0)
    tenure_months: int = Field(ge=1, le=480)
    # Client-generated UUID v4 (CLAUDE.md §4) — dedupes the application.
    idempotency_key: UUID
    # Applicant details from the onboarding wizard (SCRUM-131). Optional so a
    # bare apply still works; money is BIGINT kobo per §4.
    employment_status: EmploymentStatus | None = None
    monthly_income_kobo: int | None = Field(default=None, ge=0)


class LoanApplyResponse(BaseModel):
    loan_id: UUID
    status: str
    bank_reference_id: str | None
    requested_amount_kobo: int


class LoanItem(BaseModel):
    id: UUID
    transaction_id: UUID
    bank_partner_id: UUID
    requested_amount_kobo: int
    tenure_months: int | None
    status: str
    bank_reference_id: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: LoanRow) -> LoanItem:
        return cls(
            id=row.id,
            transaction_id=row.transaction_id,
            bank_partner_id=row.bank_partner_id,
            requested_amount_kobo=row.requested_amount_kobo,
            tenure_months=row.tenure_months,
            status=row.status,
            bank_reference_id=row.bank_reference_id,
            created_at=row.created_at,
        )


class LoanListResponse(BaseModel):
    items: list[LoanItem]
