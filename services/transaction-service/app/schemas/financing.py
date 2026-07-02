"""Response schema for the buyer financing summary (SCRUM-94)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.services.financing_summary import FinancingSummary


class PropertyOut(BaseModel):
    title: str
    property_type: str
    address_text: str
    lga: str
    state: str
    sale_type: str
    asking_price_kobo: int
    primary_image_url: str | None


class ExistingLoanOut(BaseModel):
    loan_id: UUID
    status: str


class FinancingSummaryOut(BaseModel):
    transaction_id: UUID
    stage: str
    agreed_price_kobo: int
    max_loan_kobo: int
    property: PropertyOut
    existing_loan: ExistingLoanOut | None

    @classmethod
    def from_summary(cls, s: FinancingSummary) -> FinancingSummaryOut:
        return cls(
            transaction_id=s.transaction_id,
            stage=s.stage,
            agreed_price_kobo=s.agreed_price_kobo,
            max_loan_kobo=s.max_loan_kobo,
            property=PropertyOut(
                title=s.property.title,
                property_type=s.property.property_type,
                address_text=s.property.address_text,
                lga=s.property.lga,
                state=s.property.state,
                sale_type=s.property.sale_type,
                asking_price_kobo=s.property.asking_price_kobo,
                primary_image_url=s.property.primary_image_url,
            ),
            existing_loan=(
                ExistingLoanOut(loan_id=s.existing_loan.loan_id, status=s.existing_loan.status)
                if s.existing_loan is not None
                else None
            ),
        )
