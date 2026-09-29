"""Payout-account routes (SCRUM-145, SCRUM-223). Self-scoped.

A signed-in payee (realtor / seller) registers or reads the bank account they'll
be paid into. Always the caller's own account (caller.user_id) — no id in the
path — so there is no cross-user access. The full account number is never
returned (masked to last 4).

SCRUM-223:
  * GET /payout-account/resolve — the name the BANK holds for an account, for
    the payee to confirm before saving.
  * PUT /payout-account requires `X-Reauth-Token` from auth-service's
    POST /auth/reauth, minted for THIS caller moments ago. The stored name is
    the bank's; any `account_name` in the body is ignored.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.adapters.paystack_recipient import AccountNotResolved, PaystackRecipientError
from app.dependencies import get_current_user, get_payout_account_service, get_reauth_user_id
from app.schemas.payout_account import (
    PayoutAccountRequest,
    PayoutAccountResponse,
    ResolvedAccountResponse,
)
from app.security import CurrentUser
from app.services.payout_account import PayoutAccountService

router = APIRouter(prefix="/payout-account", tags=["payout"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
PayoutServiceDep = Annotated[PayoutAccountService, Depends(get_payout_account_service)]
ReauthDep = Annotated[UUID | None, Depends(get_reauth_user_id)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


def _not_resolved() -> JSONResponse:
    return _error(
        422,
        "ACCOUNT_NOT_RESOLVED",
        "The bank doesn't recognise that account number. Check the number and the bank.",
    )


def _rail_down() -> JSONResponse:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "RECIPIENT_UNAVAILABLE",
        "Could not verify the bank account right now. Please retry.",
    )


@router.get("/resolve", response_model=None)
async def resolve_payout_account(
    caller: CurrentUserDep,
    service: PayoutServiceDep,
    account_number: Annotated[str, Query(pattern=r"^\d{10}$")],
    bank_code: Annotated[str, Query(pattern=r"^\d{3,10}$")],
) -> ResolvedAccountResponse | JSONResponse:
    """The account holder's name as the bank has it. Nothing is stored."""
    try:
        name = await service.resolve_name(account_number=account_number, bank_code=bank_code)
    except AccountNotResolved:
        return _not_resolved()
    except PaystackRecipientError:
        return _rail_down()
    return ResolvedAccountResponse(account_name=name)


@router.put("", response_model=None)
async def set_payout_account(
    payload: PayoutAccountRequest,
    request: Request,
    caller: CurrentUserDep,
    reauth_user_id: ReauthDep,
    service: PayoutServiceDep,
) -> PayoutAccountResponse | JSONResponse:
    """Register/replace the caller's payout bank account (creates its Paystack
    transfer recipient). Requires a fresh password confirmation."""
    # The reauth token must vouch for THIS account. One minted for the same
    # person's other account (SCRUM-236) does not count: the password was
    # re-entered to change that account's details, not this one's.
    if reauth_user_id is None or reauth_user_id != caller.user_id:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "REAUTH_REQUIRED",
            "Confirm your password to change your payout account.",
        )
    try:
        row = await service.set_account(
            user_id=caller.user_id,
            actor_role=caller.role,
            account_number=payload.account_number,
            bank_code=payload.bank_code,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AccountNotResolved:
        return _not_resolved()
    except PaystackRecipientError:
        return _rail_down()
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
