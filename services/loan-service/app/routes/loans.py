"""Loan application routes (SCRUM-75). POST /loans/apply + GET /loans/me."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_bank_partner_query_service,
    get_current_user,
    get_loan_application_service,
    get_loan_query_service,
    get_repayment_query_service,
)
from app.schemas.bank_partner import BankPartnerItem, BankPartnersResponse
from app.schemas.loan import LoanApplyRequest, LoanApplyResponse, LoanItem, LoanListResponse
from app.schemas.loan_detail import LoanDetailOut
from app.schemas.repayment import LoanRepaymentsOut
from app.security import CurrentUser
from app.services.bank_partner_query import BankPartnerQueryService
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
from app.services.loan_query import LoanNotFound as LoanDetailNotFound
from app.services.loan_query import LoanQueryService
from app.services.loan_query import NotLoanViewer as NotLoanDetailViewer
from app.services.repayment_query import (
    LoanNotFound,
    NotLoanViewer,
    RepaymentQueryService,
)

router = APIRouter(prefix="/loans", tags=["loans"])

BuyerDep = Annotated[CurrentUser, Depends(get_current_user)]
ServiceDep = Annotated[LoanApplicationService, Depends(get_loan_application_service)]
RepaymentsDep = Annotated[RepaymentQueryService, Depends(get_repayment_query_service)]
PartnersDep = Annotated[BankPartnerQueryService, Depends(get_bank_partner_query_service)]
LoanDetailDep = Annotated[LoanQueryService, Depends(get_loan_query_service)]


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


@router.get("/bank-partners", response_model=BankPartnersResponse)
async def bank_partners(caller: BuyerDep, service: PartnersDep) -> BankPartnersResponse:
    """Active bank partners and their loan-product details, for the buyer's
    financing calculator (SCRUM-94). Read-only; auth-gated so only signed-in
    buyers see partner terms."""
    partners = await service.list_active()
    return BankPartnersResponse(items=[BankPartnerItem.from_summary(p) for p in partners])


@router.get("/me", response_model=LoanListResponse)
async def my_loans(caller: BuyerDep, service: ServiceDep) -> LoanListResponse:
    """The caller's loan applications, newest first."""
    rows = await service.list_for_buyer(caller)
    return LoanListResponse(items=[LoanItem.from_row(r) for r in rows])


@router.get("/{loan_id}", response_model=None)
async def loan_detail(
    loan_id: UUID,
    caller: BuyerDep,
    service: LoanDetailDep,
) -> LoanDetailOut | JSONResponse:
    """Full loan detail for the buyer's status/approval page (SCRUM-94): the
    decided terms + bank name. The buyer sees only their own loan; admins any."""
    try:
        detail = await service.get_detail(loan_id, caller)
    except LoanDetailNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "LOAN_NOT_FOUND", "No such loan.")
    except NotLoanDetailViewer:
        return _error(
            status.HTTP_403_FORBIDDEN, "NOT_LOAN_VIEWER", "You can only view your own loan."
        )
    return LoanDetailOut.from_row(detail)


@router.get("/{loan_id}/repayments", response_model=None)
async def loan_repayments(
    loan_id: UUID,
    caller: BuyerDep,
    service: RepaymentsDep,
) -> LoanRepaymentsOut | JSONResponse:
    """Repayment milestones + progress for a loan. The buyer sees only their own
    loan; admins may view any (SCRUM-77). Overdue is derived at read-time."""
    try:
        view = await service.get_for_loan(loan_id, caller)
    except LoanNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "LOAN_NOT_FOUND", "No such loan.")
    except NotLoanViewer:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "NOT_LOAN_VIEWER",
            "You can only view your own loan's repayments.",
        )
    return LoanRepaymentsOut.from_view(view)
