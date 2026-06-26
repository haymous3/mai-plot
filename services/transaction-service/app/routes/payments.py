"""Buyer deposit checkout (SCRUM-83). POST /transactions/{id}/deposit."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_deposit_service
from app.schemas.payment import DepositRequest, DepositResponse
from app.security import CurrentUser
from app.services.deposit import (
    AlreadyDeposited,
    AmountMismatch,
    BuyerEmailMissing,
    DepositService,
    NotTransactionBuyer,
    TransactionNotFound,
)

router = APIRouter(prefix="/transactions", tags=["payments"])

BuyerDep = Annotated[CurrentUser, Depends(get_current_user)]
DepositServiceDep = Annotated[DepositService, Depends(get_deposit_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post("/{transaction_id}/deposit", response_model=None)
async def initiate_deposit(
    transaction_id: UUID,
    payload: DepositRequest,
    caller: BuyerDep,
    service: DepositServiceDep,
) -> DepositResponse | JSONResponse:
    """Initialise a Paystack checkout for the buyer's full escrow deposit."""
    try:
        result = await service.initiate(
            transaction_id=transaction_id,
            buyer=caller,
            idempotency_key=payload.idempotency_key,
            amount_kobo=payload.amount_kobo,
        )
    except TransactionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", "No such transaction.")
    except NotTransactionBuyer:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_TRANSACTION_BUYER",
            "Only the buyer can fund this deal's escrow.",
        )
    except AmountMismatch:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "AMOUNT_MISMATCH",
            "The deposit must equal the agreed price.",
        )
    except AlreadyDeposited:
        return _error(
            status.HTTP_409_CONFLICT, "ALREADY_DEPOSITED", "This deposit already completed."
        )
    except BuyerEmailMissing:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUYER_EMAIL_MISSING",
            "No email on file for the buyer.",
        )
    return DepositResponse(
        authorization_url=result.authorization_url,
        reference=result.reference,
        payment_event_id=result.payment_event_id,
    )
