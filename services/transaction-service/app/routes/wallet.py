"""Read-only buyer wallet routes (SCRUM-95).

GET /wallet/summary + GET /wallet/payments — the buyer's own escrow/invested
totals, active property payments, and payment history. Scoped to the caller;
no writes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_wallet_service
from app.schemas.wallet import PaymentsOut, WalletSummaryOut
from app.security import CurrentUser
from app.services.wallet import WalletService

router = APIRouter(prefix="/wallet", tags=["wallet"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
WalletServiceDep = Annotated[WalletService, Depends(get_wallet_service)]


@router.get("/summary", response_model=WalletSummaryOut)
async def wallet_summary(caller: CurrentUserDep, service: WalletServiceDep) -> WalletSummaryOut:
    """The caller's wallet overview: in-escrow / total-invested totals + active
    property payments (paid vs. agreed)."""
    return await service.summary(caller.user_id)


@router.get("/payments", response_model=PaymentsOut)
async def wallet_payments(caller: CurrentUserDep, service: WalletServiceDep) -> PaymentsOut:
    """The caller's payment history (deposits/refunds), newest first."""
    return await service.payments(caller.user_id)
