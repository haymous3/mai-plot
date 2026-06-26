"""Loan application routes (SCRUM-75). POST /loans/apply + GET /loans/me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_loan_application_service
from app.schemas.loan import LoanApplyRequest, LoanApplyResponse, LoanItem, LoanListResponse
from app.security import CurrentUser
from app.services.loan_application import (
    BankPartnerUnavailable,
    DailyLimitReached,
    LoanApplicationService,
    LoanBandViolation,
    LoanCapExceeded,
    NotTransactionBuyer,
    TenureViolation,
    TransactionNotFound,
)

router = APIRouter(prefix="/loans", tags=["loans"])

BuyerDep = Annotated[CurrentUser, Depends(get_current_user)]
ServiceDep = Annotated[LoanApplicationService, Depends(get_loan_application_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post("/apply", response_model=None)
async def apply_for_loan(
    payload: LoanApplyRequest,
    caller: BuyerDep,
    service: ServiceDep,
) -> LoanApplyResponse | JSONResponse:
    """Apply for a soft loan (up to 50% of the agreed price) via a bank partner."""
    try:
        result = await service.apply(
            buyer=caller,
            transaction_id=payload.transaction_id,
            bank_partner_id=payload.bank_partner_id,
            requested_amount_kobo=payload.requested_amount_kobo,
            tenure_months=payload.tenure_months,
            idempotency_key=payload.idempotency_key,
        )
    except TransactionNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", "No such transaction.")
    except NotTransactionBuyer:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_TRANSACTION_BUYER",
            "Only the buyer can apply for this deal's loan.",
        )
    except LoanCapExceeded:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "LOAN_CAP_EXCEEDED",
            "The loan cannot exceed 50% of the agreed price.",
        )
    except BankPartnerUnavailable:
        return _error(
            status.HTTP_404_NOT_FOUND, "BANK_PARTNER_UNAVAILABLE", "No such active bank partner."
        )
    except LoanBandViolation:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "LOAN_BAND_VIOLATION",
            "The amount is outside the partner's loan band.",
        )
    except TenureViolation:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "TENURE_VIOLATION",
            "The tenure is outside the partner's allowed range.",
        )
    except DailyLimitReached:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "DAILY_LIMIT_REACHED",
            "You've reached today's loan-application limit.",
        )
    return LoanApplyResponse(
        loan_id=result.loan_id,
        status=result.status,
        bank_reference_id=result.bank_reference_id,
        requested_amount_kobo=result.requested_amount_kobo,
    )


@router.get("/me", response_model=LoanListResponse)
async def my_loans(caller: BuyerDep, service: ServiceDep) -> LoanListResponse:
    """The caller's loan applications, newest first."""
    rows = await service.list_for_buyer(caller)
    return LoanListResponse(items=[LoanItem.from_row(r) for r in rows])
