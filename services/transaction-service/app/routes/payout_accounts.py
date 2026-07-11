"""Payout-account routes (SCRUM-145). PUT/GET /payout-account — self-scoped.

A signed-in payee (realtor / seller) registers or reads the bank account they'll
be paid into. Always the caller's own account (caller.user_id) — no id in the
path — so there is no cross-user access. The full account number is never
returned (masked to last 4).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.adapters.paystack_recipient import PaystackRecipientError
from app.dependencies import get_current_user, get_payout_account_service
from app.schemas.payout_account import PayoutAccountRequest, PayoutAccountResponse
from app.security import CurrentUser
from app.services.payout_account import PayoutAccountService

router = APIRouter(prefix="/payout-account", tags=["payout"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
PayoutServiceDep = Annotated[PayoutAccountService, Depends(get_payout_account_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.put("", response_model=None)
async def set_payout_account(
    payload: PayoutAccountRequest, caller: CurrentUserDep, service: PayoutServiceDep
) -> PayoutAccountResponse | JSONResponse:
    """Register/replace the caller's payout bank account (creates its Paystack
    transfer recipient)."""
    try:
        row = await service.set_account(
            user_id=caller.user_id,
            account_number=payload.account_number,
            bank_code=payload.bank_code,
            account_name=payload.account_name,
        )
    except PaystackRecipientError:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "RECIPIENT_UNAVAILABLE",
            "Could not verify the bank account right now. Please retry.",
        )
    return PayoutAccountResponse.from_row(row)


@router.get("", response_model=None)
async def get_payout_account(
    caller: CurrentUserDep, service: PayoutServiceDep
) -> PayoutAccountResponse | JSONResponse:
    """The caller's payout account, or 404 if they haven't set one."""
    row = await service.get_account(caller.user_id)
    if row is None:
        return _error(
            status.HTTP_404_NOT_FOUND, "PAYOUT_ACCOUNT_NOT_FOUND", "No payout account on file."
        )
    return PayoutAccountResponse.from_row(row)
