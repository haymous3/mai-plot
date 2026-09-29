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
    # IGNORED since SCRUM-223 — the stored name is the one the BANK returns.
    # Still accepted so a client from before the change does not 422 mid-deploy.
    account_name: str | None = Field(default=None, max_length=200)


class ResolvedAccountResponse(BaseModel):
    """GET /payout-account/resolve — the name the bank holds for the account,
    shown to the payee to confirm before they save."""

    account_name: str


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
