"""Schemas for payout-account management (SCRUM-145).

The full account number is financial PII and is never returned — responses show
only the masked last 4 digits.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.repositories.payout_account_repo import PayoutAccountRow


class PayoutAccountRequest(BaseModel):
    # NUBAN account numbers are 10 digits; bank codes are short numeric strings.
    account_number: str = Field(pattern=r"^\d{10}$")
    bank_code: str = Field(pattern=r"^\d{3,10}$")
    account_name: str = Field(min_length=1, max_length=200)


class PayoutAccountResponse(BaseModel):
    account_number_masked: str
    bank_code: str
    account_name: str
    # True once a Paystack transfer recipient exists for the account (payouts can
    # target it). False if the recipient hasn't been created yet.
    recipient_ready: bool

    @classmethod
    def from_row(cls, row: PayoutAccountRow) -> PayoutAccountResponse:
        return cls(
            account_number_masked=f"••••{row.account_number[-4:]}",
            bank_code=row.bank_code,
            account_name=row.account_name,
            recipient_ready=row.recipient_code is not None,
        )
